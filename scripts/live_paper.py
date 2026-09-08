import argparse
import sys
from dotenv import load_dotenv
import os


def main():
    parser = argparse.ArgumentParser(description="Live Paper CLI")
    parser.add_argument("action", choices=["status", "arm", "disarm"])
    args = parser.parse_args()

    load_dotenv()

    execution_mode = os.getenv("EXECUTION_MODE", "local_paper")
    api_key = os.getenv("ALPACA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET_KEY")

    if args.action == "status":
        print(f"Execution Mode: {execution_mode}")
        print(f"Credentials Present: {bool(api_key and secret)}")
    elif args.action == "arm":
        if execution_mode != "alpaca_paper":
            print("ERROR: EXECUTION_MODE must be alpaca_paper")
            sys.exit(1)
        if not api_key or not secret:
            print("ERROR: ALPACA credentials missing")
            sys.exit(1)
        print("System ARMED for Live Paper Trading")
    elif args.action == "disarm":
        print("System DISARMED")


if __name__ == "__main__":
    main()
