import click
import yaml
from fonz.connection import Fonz


class CommandWithConfig(click.Command):
    def invoke(self, ctx):
        click.echo(ctx.params)
        config_filename = ctx.params.get("config_file")
        if config_filename is not None:
            with open(config_filename) as file:
                config = yaml.safe_load(file)
                for param, value in ctx.params.items():
                    if value is None and param in config:
                        ctx.params[param] = config[param]

        return super(CommandWithConfig, self).invoke(ctx)


@click.group()
def cli():
    pass


@click.command(cls=CommandWithConfig)
@click.option("--base-url", envvar="LOOKER_BASE_URL")
@click.option("--client-id", envvar="LOOKER_CLIENT_ID")
@click.option("--client-secret", envvar="LOOKER_CLIENT_SECRET")
@click.option("--config-file")
@click.option("--port", default=19999)
@click.option("--api-version", default="3.0")
def connect(base_url, client_id, client_secret, config_file, port, api_version):
    client = Fonz(base_url, client_id, client_secret, port, api_version)
    client.connect()


@click.command(cls=CommandWithConfig)
@click.option("--project", envvar="LOOKER_PROJECT")
@click.option("--branch", envvar="LOOKER_GIT_BRANCH")
@click.option("--base-url", envvar="LOOKER_BASE_URL")
@click.option("--client-id", envvar="LOOKER_CLIENT_ID")
@click.option("--client-secret", envvar="LOOKER_CLIENT_SECRET")
@click.option("--config-file")
@click.option("--port", default=19999)
@click.option("--api-version", default="3.0")
def sql(
    project, branch, base_url, client_id, client_secret, config_file, port, api_version
):
    client = Fonz(
        base_url, client_id, client_secret, port, api_version, project, branch
    )
    client.connect()
    client.update_session()
    explores = client.get_explores()

    # Get Dimensions and build query for each explore
    for explore in explores:
        explore["dimensions"] = client.get_dimensions(
            explore["model"], explore["explore"]
        )
        explore["query_id"] = client.create_query(
            explore["model"], explore["explore"], explore["dimensions"]
        )
        explore["result"] = validate_explore(explore["query_id"])

        if explore["result"]["failed"]:
            logging.info(
                "Error in explore {}: {}".format(
                    explore["explore"], explore["result"]["error"]
                )
            )

    client.print_results(explores)


cli.add_command(connect)
cli.add_command(sql)

if __name__ == "__main__":
    cli()
