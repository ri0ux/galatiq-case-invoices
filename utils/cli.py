import argparse


def parse_cli_args():
    parser = argparse.ArgumentParser(
        description="AI Invoice Processing System"
    )

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--invoice_path",
        type=str,
        help="Path to a single invoice file"
    )

    group.add_argument(
        "--invoice_dir",
        type=str,
        help="Path to a directory containing invoice files"
    )

    return parser.parse_args()