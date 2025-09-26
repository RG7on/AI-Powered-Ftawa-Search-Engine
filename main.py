from __future__ import annotations

import sys
from pathlib import Path

from dependencies.installer import run as ensure_dependencies


def run_downloads() -> None:
    from download.downloader import run as execute_downloads

    execute_downloads()


def clear_console() -> None:
    print("\033[2J\033[H", end="")


def wait_for_enter() -> None:
    input("\nPress Enter to continue...")


def menu() -> None:
    options = {
        "1": ("Download YouTube playlists", run_downloads, True),
        "2": ("Install project dependencies", ensure_dependencies, False),
        "q": ("Quit", None, False),
    }

    while True:
        clear_console()
        print("AI-Powered Ftawa Search Engine")
        print("=" * 35)
        for key, (label, _, _) in options.items():
            print(f"[{key}] {label}")

        choice = input("\nSelect an option: ").strip().lower()
        action = options.get(choice)

        if not action:
            print("Invalid choice. Try again.")
            wait_for_enter()
            continue

        label, callback, require_dependencies = action

        if choice == "q":
            print("Goodbye!")
            return

        print(f"\nStarting: {label}\n")
        try:
            if callback is None:
                return

            if require_dependencies:
                deps_ok = ensure_dependencies()
                if not deps_ok:
                    print("Dependencies missing. Exiting application.")
                    return

            result = callback()
            if callback is ensure_dependencies and result is False:
                print("Dependencies were not installed. Exiting application.")
                return
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}")
        wait_for_enter()


if __name__ == "__main__":
    repo_root = Path(__file__).parent
    sys.path.insert(0, str(repo_root))
    menu()
