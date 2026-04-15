"""
pkit.cmds.help

Display help for pkit or a specific subcommand.

[[subcmd.description]]
Display usage information for the main `pkit` command or for a
specific subcommand.

When invoked without arguments, `help` shows the top-level
command overview.

When a subcommand name is supplied, help for that command
is displayed.

This command is functionally equivalent to invoking `--help`,
but provides a consistent entry point for scripted or
explicit help access.

[[subcmd.examples]]
Examples:

```bash
Show top-level help:
    pkit help

Show help for a specific subcommand:
    pkit help add

Equivalent using the standard flag:
    pkit add --help
```

INTERNAL

:copyright: Copyright (c) 2025 John Fogelin. All rights reserved. See AUTHORS.
:license: PROPRIETARY, see LICENSE for details.
"""

import pkit.ui as click


@click.command()
@click.argument("topic", required=False)
@click.pass_context
def cmd(click_ctx, topic):
    """
    Display help for pkit or a named subcommand.
    """
    # root command (pkit)
    root = click_ctx.find_root().command

    command = root
    info_name = root.name

    if topic:
        command = root.get_command(click_ctx, topic)
        if command is None:
            raise click.UsageError(f"No such command '{topic}'")
        info_name = f"{root.name} {topic}"

    # create fresh context for correct usage rendering
    help_ctx = click.Context(command, info_name=info_name)

    click.echo(command.get_help(help_ctx))
    click_ctx.exit(0)
