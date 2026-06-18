# Rubble Language Support for VS Code

Syntax highlighting, bracket matching, and snippets for `.rbl` files.

## Features

- Full syntax highlighting for all Rubble keywords, types, and literals
- Interpolated string highlighting (`f"hello {name}"`)
- Stdlib module highlighting (`canvas`, `math`, `rand`, etc.)
- Code snippets for common patterns
- Bracket auto-close and comment toggling

## Install

Copy the `vscode-rubble` folder into:
- Windows: `%USERPROFILE%\.vscode\extensions\`
- macOS/Linux: `~/.vscode/extensions/`

Then restart VS Code.

## Snippets

| Prefix      | Description                  |
|-------------|------------------------------|
| `recipe`    | Define a recipe (function)   |
| `blueprint` | Define a blueprint (struct)  |
| `slot`      | Declare a variable           |
| `lock`      | Declare a constant           |
| `if`        | If statement                 |
| `ifelse`    | If-else statement            |
| `loop`      | While-style loop             |
| `for`       | For-in loop                  |
| `match`     | Match/switch statement       |
| `fstr`      | Interpolated string          |
| `gameloop`  | Canvas game loop skeleton    |
