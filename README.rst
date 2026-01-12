KeyClaw
=======

.. contents:: Table of Contents

Introduction
------------

This is a pentesting tool for Keycloak.
This tool may only be used for legal purposes. Do not test third-party systems without prior authorization.

About
~~~~~

KeyClaw performs **brute force** attacks against the Keycloak login API.
Results are interpreted based on HTTP status code:
- A login failure should return 401
- A successful login should return 200

Other status codes may occur, for example as a result of rate limiting on the target server.
KeyClaw will stop if an exception occurs, or an unexpected HTTP status code is received. It is up to you to troubleshoot and fine-tune usage accordingly.

Installation
~~~~~~~~~~~~

The recommended way is to create a **virtual environment** for Python and install the dependencies inside the virtual environment:

.. code:: bash

   python3 -m venv .venv
   source .venv/bin/activate
   # install the required dependencies inside the venv
   python3 -m pip install -r requirements.txt

Usage
-----

At a minimum, KeyClaw needs a valid URL for a Keycloak API endpoint and:
- either a single user, and a file containing a list of passwords
- or a combo file containing user/password pairs

First of all, it is recommended to test before launching a scan.

- By default, KeyClaw spoofs the **user agent** string. However, you can specify additional **headers**, for example a bug bounty header.
- KeyClaw runs only one thread by default. Use the `--threads` flag to set a different number of threads.
- Rate limiting: to throttle requests, use the `--pause` flag to throttle requests, followed by a value in milliseconds.

List of flags
~~~~~~~~~~~~~

- `--url`: URL of Keycloak API endpoint - required
- `--realms`: List of realms to test, comma-separated eg: `master,dev,test` (default: master)
- `--threads`: Number of threads to use (default: 1)
- `--pause`: Number of milliseconds to wait between request (per thread) (default: 0)
- `--header`: Add custom header, this option may be repeated as many times as necessary (default: none)
- `--user`: Single user to test eg: admin - may not be used with `--user-password-file`. This option requires `--password-file`
- `--password-file`: File containing list of passwords. To be used along with `--user`
- `--user-password-file`: File containing list of users AND passwords (typically colon-delimited) - may not be used with `--password-file`
- `--delimiter`: Delimiter for `--user-password-file` (default: `:`)
- `--stop-on-success`: stop after one successful login

Examples
~~~~~~~~

Try user admin, single-threaded:

.. code:: bash

    python3 keyclaw.py --url http://localhost:8080 --user admin --password-file /path/to/passwords.txt

A more complete example: resuming from the 100th line of the password file, use 5 threads, wait 200ms between requests, add one customer header:

.. code:: bash

   python3 keyclaw.py --url http://localhost:8080 --start-from 100 --user admin --password-file /path/to/passwords.txt --threads 5 --pause 200 --realms master,dev --header "X-BugBounty: <your token>"

Tips and tricks
~~~~~~~~~~~~~~~

- It is a good idea to test this script on your own Keycloak instance (use Docker or ready to use virtual images to set up a test environment)
- If the process is interrupted for any reason, use the `--start-from` flag to resume
- If you suspect a WAF (web application firewall) is interfering, you may be able to bypass it by spoofing headers and throttling requests on your end
- Use the `--pause` flag to wait between requests (expressed in *milliseconds*)

Limitations
~~~~~~~~~~~

- Keyclaw uses the requests library, therefore it does not support HTTP/2.0
- The login API may be disabled on some systems

References
----------

- `Keycloak Open Source Identity and Access Management <https://www.keycloak.org/>`_
- `Pentesting Keycloak Part 1: Identifying Misconfiguration Using Risk Management Tools <https://csacyber.com/blog/pentesting-keycloak-part-1-identifying-misconfiguration-using-risk-management-tools>`_
- `Pentesting Keycloak – Part 2: Identifying Misconfiguration Using Risk Management Tools <https://csacyber.com/blog/pentesting-keycloak-part-2>`_
