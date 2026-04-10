from jobpipe.cli import main


if __name__ == "__main__":
    exit_code = main()
    if exit_code:
        raise SystemExit(exit_code)
