# RIDP Form Platform - Postman Runner Guide

This guide provides instructions on how to use the Postman runner script to validate the backend API.

## Prerequisites

- Node.js and npm (already installed)
- `make up-dev` running the backend (required for tests to pass)

## How to use

1.  Grant execute permission to the script:
    ```bash
    chmod +x postman_runner.sh
    ```

2.  Run the tests:
    ```bash
    ./postman_runner.sh
    ```

3.  Observe the CLI output. All results are automatically saved to:
    - `postman_run.log`: Full console output (useful for debugging).
    - `postman_results.json`: Detailed machine-readable JSON results.

## Sharing results

If you encounter any issues or failures, please share the contents of:
- `postman_run.log`
- `postman_results.json`

This will help the AI agent diagnose and fix the specific issues in the backend implementation.
