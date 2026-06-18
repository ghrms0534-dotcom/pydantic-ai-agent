import argparse
import asyncio
import sys

from backend.app.agent.runner import run_agent


def configure_output_encoding() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


async def async_main(prompt: str) -> None:
    result = await run_agent(prompt)
    print(result)


async def chat_loop() -> None:
    print("Local AI Agent chat started. Type 'quit' to exit.")
    while True:
        prompt = input("\n> ").strip()
        if prompt.lower() in {"quit", "exit"}:
            print("bye")
            return
        if not prompt:
            continue

        result = await run_agent(prompt)
        print(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MAOS, the Multi-Agent Autonomous Runtime.")
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt to send to the local agent.",
    )
    return parser


def cli() -> None:
    configure_output_encoding()
    args = build_parser().parse_args()
    if args.prompt:
        asyncio.run(async_main(prompt=" ".join(args.prompt)))
        return

    asyncio.run(chat_loop())


if __name__ == "__main__":
    cli()
