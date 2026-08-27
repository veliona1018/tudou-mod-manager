"""Open a native Windows folder picker and print the selected path."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog


def choose_folder() -> str:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(title="选择 L4D2 Mod 文件夹")
    root.destroy()
    return selected or ""


def main() -> None:
    selected = choose_folder()
    if selected:
        print(selected)


if __name__ == "__main__":
    main()
