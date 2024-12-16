import click
import asyncio
from .schema_generator import SchemaGenerator

@click.command()
@click.option('--config', default='config.yaml', help='Path to configuration file')
def main(config):
    """Generate MongoDB schema documentation."""
    try:
        generator = SchemaGenerator(config)
        asyncio.run(generator.generate_schemas())
        click.echo("Schema generation completed successfully!")
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.Abort()

if __name__ == '__main__':
    main()
