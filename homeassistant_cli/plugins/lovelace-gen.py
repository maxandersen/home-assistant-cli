import collections
import logging
import os
from pathlib import Path
import sys
import time

import click
from homeassistant_cli.cli import pass_context
import jinja2
import ruamel.yaml
from ruamel.yaml import YAML
from ruamel.yaml.constructor import RoundTripConstructor, SafeConstructor

_LOGGING = logging.getLogger(__name__)
MAIN_FILE = 'main.yaml'
GENERATOR_MESSAGE = """
# This file is automatically generated by lovelace-gen.py
# https://github.com/thomasloven/homeassistant-lovelace-gen
# Any changes made to it will be overwritten the next time the script is run.
"""


def my_compose_document(self):
    self.get_event()
    node = self.compose_node(None, None)
    self.get_event()
    # self.anchors = {}    # <<<< commented out
    return node


ruamel.yaml.RoundTripLoader.compose_document = my_compose_document


def get_input_dir(inp):
    if not inp:
        if os.path.exists(os.path.join('/config/lovelace', MAIN_FILE)):
            return '/config/lovelace'
        if os.path.exists(os.path.join('lovelace/', MAIN_FILE)):
            return 'lovelace/'

    if os.path.exists(os.path.join(inp, MAIN_FILE)):
        return inp
    print("Input file main.yaml not found.", file=sys.stderr)
    sys.exit(2)


def process_file(jinja, yaml, path):
    template = jinja.get_template(path)
    return yaml.load(template.render())


def include_statement(loader, node):
    global jinja, yaml
    y = loader.loader
    yaml = YAML(typ=y.typ, pure=y.pure)  # same values as including YAML
    yaml.preserve_quotes = True
    yaml.composer.anchors = loader.composer.anchors
    return process_file(jinja, yaml, node.value)


def file_statement(loader, node):
    path = node.value
    timestamp = time.time()
    if '?' in path:
        return f'{path}&{str(timestamp)}'
    else:
        return f'{path}?{str(timestamp)}'


def secret_statement(loader, node):
    global yaml, secrets
    if not secrets:
        secrets = yaml.load(open(os.path.join(inp, '..', 'secrets.yaml')))
    if not node.value in secrets:
        raise yaml.scanner.ScannerError(
            'Could not find secret {}'.format(node.value)
        )
    return secrets[node.value]


@click.command('lovelace-gen')
@click.argument("input", required=False)
@click.option("output", "-o", "--output", help="Output file")
@pass_context
def cli(ctx, input, output):
    """Generate ui-lovelace.yaml from lovelace/main.yaml

       <input directory> is optional, defaults to '/lovelace' or '/config/lovelace'
    """

    global jinja, yaml, inp

    #    ruamel.yaml.representer.RoundTripRepresenter.add_representer(
    #        collections.OrderedDict,
    #        ruamel.yaml.representer.RoundTripRepresenter.represent_ordereddict)

    inp = get_input_dir(input)
    outp = output or os.path.join(inp, '..', 'ui-lovelace.yaml')

    jinja = jinja2.Environment(loader=jinja2.FileSystemLoader(inp))
    yaml = YAML(typ='rt')
    yaml.preserve_quotes = True
    yaml.Constructor = RoundTripConstructor

    RoundTripConstructor.add_constructor("!include", include_statement)
    RoundTripConstructor.add_constructor("!file", file_statement)

    try:
        data = process_file(jinja, yaml, MAIN_FILE)
    except Exception as e:
        _LOGGING.error("Processing of yaml failed.")
        _LOGGING.exception(e)
        sys.exit(3)

    try:
        with open(outp, 'w') as fp:
            fp.write(GENERATOR_MESSAGE)
            yaml.dump(data, fp)
    except Exception as e:
        _LOGGING.error("Writing ui-lovelace.yaml failed.")
        _LOGGING.exception(e)
        sys.exit(4)
