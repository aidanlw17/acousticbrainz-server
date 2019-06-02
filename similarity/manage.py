from __future__ import print_function
from flask.cli import FlaskGroup
import click

import webserver
import metrics
from operations import HybridMetric
from index_model import AnnoyModel
import db

from sqlalchemy import text


PROCESS_BATCH_SIZE = 50000

cli = FlaskGroup(add_default_commands=False, create_app=webserver.create_app_flaskgroup)


@cli.command()
def init_similarity():
    click.echo('Copying data')
    with db.engine.begin() as connection:
        connection.execute("INSERT INTO similarity(id) SELECT id FROM lowlevel")


def _get_recordings_without_similarity(connection, name, batch_size):
    result = connection.execute("SELECT id FROM similarity WHERE %(metric)s IS NULL LIMIT %(limit)s"
                                % {'metric': name, 'limit': batch_size})
    rows = result.fetchall()
    if not rows:
        return []
    ids = zip(*rows)[0]
    return ids


def _update_similarity(connection, name, row_id, vector, isnan=False):
    value = '[' + ', '.join(["'NaN'::double precision"] * len(vector)) + ']' if isnan else str(list(vector))
    connection.execute("UPDATE similarity SET %(metric)s = %(value)s WHERE id = %(id)s" %
                       {'metric': name, 'value': 'ARRAY' + value, 'id': row_id})


@cli.command(name='add-metric')
@click.argument("name")
@click.option("--force", "-f", is_flag=True, help="Recompute existing metrics.")
@click.option("--to-process", "-t", type=int, help="Only process limited number of rows")
@click.option("--batch-size", "-b", type=int, help="Override processing batch size")
def add_metric(name, force=False, to_process=None, batch_size=None):
    try:
        metric_cls = metrics.BASE_METRICS[name]
    except KeyError:
        click.echo("No such metric is implemented: {}".format(name))
        return

    with db.engine.connect() as connection:
        metric = metric_cls(connection)
        metric.create(clear=force)

        result = connection.execute("SELECT count(*), count(%s) FROM similarity" % name)
        total, past = result.fetchone()
        current = past
        to_process = to_process or total - past

        try:
            metric.calculate_stats()
        except AttributeError:
            pass

        batch_size = batch_size or PROCESS_BATCH_SIZE

        click.echo('Started processing, {} / {} ({:.3f}%) already processed'.format(
            current, total, float(current) / total * 100))
        ids = _get_recordings_without_similarity(connection, name, batch_size)

        while len(ids) > 0 and (current - past < to_process):
            with connection.begin():
                for row_id, data in metric.get_data_batch(ids):
                    try:
                        vector = metric.transform(data)
                        isnan = False
                    except ValueError:
                        vector = [None] * metric.length()
                        isnan = True
                    _update_similarity(connection, name, row_id, vector, isnan=isnan)

            current += len(ids)

            click.echo('Processing {} / {} ({:.3f}%)'.format(current, total, float(current) / total * 100))
            ids = _get_recordings_without_similarity(connection, name, batch_size)

    return current


@cli.command(name='delete-metric')
@click.argument("name")
@click.option("--soft", "-s", is_flag=True, help="Don't delete data")
@click.option("--leave-stats", "-l", is_flag=True, help="Don't delete computed statistics")
def delete_metric(name, soft=False, leave_stats=False):
    try:
        metric_cls = metrics.BASE_METRICS[name]
    except KeyError:
        click.echo('No such metric is implemented: {}'.format(name))
        return

    with db.engine.begin() as connection:
        metric = metric_cls(connection)
        metric.delete(soft=soft)

        if not leave_stats:
            try:
                metric.delete_stats()
            except AttributeError:
                pass


@cli.command()
@click.argument("name")
@click.argument("category")
@click.option("--description", "-d", type=str, help="Description of metric")
def add_hybrid(name, category, description=None):
    description = description or name
    with db.engine.begin() as connection:
        metric = HybridMetric(connection, name, category, description)
        metric.create()


@cli.command()
@click.argument("name")
def delete_hybrid(name):
    with db.engine.begin() as connection:
        metric = HybridMetric(connection, name)
        metric.delete()


@cli.command(name='add-index')
@click.argument("metric")
@click.option("batch_size", "-b", type=int, help="Size of batches")
def add_index(metric, batch_size=None):
    """Creates an annoy index for the specified metric, adds all items to the index."""
    with db.engine.connect() as connection:
        click.echo("Initializing index...")
        index = AnnoyModel(connection, metric)

        batch_size = batch_size or PROCESS_BATCH_SIZE
        offset = 0
        count = 0

        result = connection.execute("""
            SELECT MAX(id)
              FROM similarity
        """)
        total = result.fetchone()[0]

        batch_query = text("""
            SELECT *
              FROM similarity
             ORDER BY id
             LIMIT :batch_size
            OFFSET :offset
        """)

        click.echo("Inserting items...")
        while True:
            # Get ids and vectors for specific metric in batches
            batch_result = connection.execute(batch_query, { "batch_size": batch_size, "offset": offset })
            if not batch_result.rowcount:
                click.echo("Finished adding items. Building index...")
                break

            items = []
            for row in batch_result.fetchall():
                items.append((row["id"], row[index.metric_name]))        

            for id, vector in items:
                while not id == count:
                    # Rows are empty, add zero vector
                    placeholder = [0] * index.dimension
                    index.add_recording(count, placeholder)
                    count += 1
                index.add_recording(id, vector)
                count += 1
            
            offset += batch_size
            click.echo("Items added: {}/{} ({:.3f}%)".format(offset, total, float(offset) / total * 100))
        
        index.build()
        click.echo("Saving index...")
        index.save()
        click.echo("Done!")
