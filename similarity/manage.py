from __future__ import print_function
from flask.cli import FlaskGroup
import click

import webserver
import metrics
import db
import db.similarity

cli = FlaskGroup(add_default_commands=False, create_app=webserver.create_app_flaskgroup)


@cli.command(name="add-metrics")
@click.option("--force", "-f", is_flag=True, help="Recompute existing metrics.")
@click.option("--batch-size", "-b", type=int, help="Override processing batch size.")
def add_metrics(force=False, batch_size=None):
    """Computes all 12 base metrics for each recording
    in the lowlevel table, inserting these values in
    the similarity table."""
    click.echo("Adding all metrics...")
    db.similarity.add_metrics(force=force, batch_size=batch_size)
    click.echo("Finished adding all metrics, exiting...")


@cli.command(name="update-metric")
@click.argument("metric")
@click.option("--batch-size", "-b", type=int, help="Override processing batch size.")
def update_metric(metric, batch_size=None):
    """Recomputes and updates a single metric in the
    similarity table for all recordings."""
    click.echo("Computing metric {}".format(metric))
    pass
    click.echo("Finished updating metric, exiting...")


@cli.command(name="delete-metric")
@click.argument("metric")
@click.option("--soft", "-s", is_flag=True, help="Don't delete data.")
@click.option("--leave-stats", "-l", is_flag=True, help="Don't delete computed statistics.")
def delete_metric(name, soft=False, leave_stats=False):
    """Deletes the metric specified by the `metric` argument."""
    try:
        metric_cls = metrics.BASE_METRICS[metric]
    except KeyError:
        click.echo('No such metric is implemented: {}'.format(metric))
        return

    with db.engine.begin() as connection:
        metric = metric_cls(connection)
        metric.delete(soft=soft)

        if not leave_stats:
            try:
                metric.delete_stats()
            except AttributeError:
                pass