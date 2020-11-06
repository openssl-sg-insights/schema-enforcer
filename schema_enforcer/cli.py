"""main cli commands."""
import sys

import click
from termcolor import colored

from schema_enforcer.utils import MutuallyExclusiveOption
from schema_enforcer import config
from schema_enforcer.schemas.manager import SchemaManager
from schema_enforcer.instances.file import InstanceFileManager
from schema_enforcer.ansible_inventory import AnsibleInventory
from schema_enforcer.utils import error


@click.group()
def main():
    """SCHEMA ENFORCER.

    This tool is used to ensure data adheres to a schema definition. The data can come
    from YAML files, JSON files, or an Ansible inventory. The schema to which the data
    should adhere can currently be defined using the JSONSchema language in YAML or JSON
    format.
    """


@click.option("--show-pass", default=False, help="Shows validation checks that passed", is_flag=True, show_default=True)
@click.option(
    "--strict",
    default=False,
    help="Forces a stricter schema check that warns about unexpected additional properties",
    is_flag=True,
    show_default=True,
)
@click.option(
    "--show-checks",
    default=False,
    help="Shows the schemas to be checked for each instance file",
    is_flag=True,
    show_default=True,
)
@main.command()
def validate(show_pass, show_checks, strict):
    r"""Validates instance files against defined schema.

    \f

    Args:
        show_pass (bool): show successful schema validations
        show_checks (bool): show schemas which will be validated against each instance file
        strict (bool): Forces a stricter schema check that warns about unexpected additional properties
    """
    config.load()

    # ---------------------------------------------------------------------
    # Load Schema(s) from disk
    # ---------------------------------------------------------------------
    smgr = SchemaManager(config=config.SETTINGS)

    if not smgr.schemas:
        error("No schemas were loaded")
        sys.exit(1)

    # ---------------------------------------------------------------------
    # Load Instances
    # ---------------------------------------------------------------------
    ifm = InstanceFileManager(config=config.SETTINGS)

    if not ifm.instances:
        error("No instance files were found to validate")
        sys.exit(1)

    if show_checks:
        ifm.print_schema_mapping()
        sys.exit(0)

    error_exists = False
    for instance in ifm.instances:
        for result in instance.validate(smgr, strict):

            result.instance_type = "FILE"
            result.instance_name = instance.filename
            result.instance_location = instance.path

            if not result.passed():
                error_exists = True
                result.print()

            elif result.passed() and show_pass:
                result.print()

    if not error_exists:
        print(colored("ALL SCHEMA VALIDATION CHECKS PASSED", "green"))
    else:
        sys.exit(1)


@click.option(
    "--list",
    "list_schemas",
    default=False,
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["generate_invalid", "check"],
    help="List all available schemas",
    is_flag=True,
)
@click.option(
    "--check",
    default=False,
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["generate_invalid", "list", "schema"],
    help="Validates that all schemas are valid (spec and unit tests)",
    is_flag=True,
)
@click.option(
    "--generate-invalid",
    default=False,
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["check", "list"],
    help="Generates expected invalid data from a given schema [--schema]",
    is_flag=True,
)
@click.option("--schema", help="The name of a schema.")
@main.command()
def schema(check, generate_invalid, list_schemas):
    r"""Manage your schemas.

    \f

    Args:
        check (bool): Validates that all schemas are valid (spec and unit tests)
        generate_invalid (bool): Generates expected invalid data from a given schema
        list (bool): List all available schemas
    """
    config.load()

    # ---------------------------------------------------------------------
    # Load Schema(s) from disk
    # ---------------------------------------------------------------------
    smgr = SchemaManager(config=config.SETTINGS)

    if not smgr.schemas:
        error("No schemas were loaded")
        sys.exit(1)

    if list_schemas:
        smgr.print_schemas_list()
        sys.exit(0)

    if generate_invalid:
        if not schema:
            sys.exit(
                "Please indicate the name of the schema you'd like to generate the invalid data for using --schema"
            )
        smgr.generate_invalid_tests_expected(schema_id=schema)
        sys.exit(0)

    if check:
        smgr.test_schemas()
        sys.exit(0)


@main.command()
@click.option("--inventory", "-i", help="Ansible inventory file.", required=False)
@click.option("--host", "-h", "limit", help="Limit the execution to a single host.", required=False)
@click.option("--show-pass", default=False, help="Shows validation checks that passed", is_flag=True, show_default=True)
def ansible(inventory, limit, show_pass):  # pylint: disable=too-many-branches,too-many-locals
    r"""Validate the hostvar for all hosts within an Ansible inventory.

    The hostvar are dynamically rendered based on groups.
    For each host, if a variable `jsonschema_mapping` is defined, it will be used
    to determine which schemas should be use to validate each key.
    \f

    Args:
        inventory (string): The name of the inventory file to validate against
        limit (string, None): Name of a host to limit the execution to
        show_pass (bool): Shows validation checks that passed Default to False

    Example:
        $ cd examples/ansible
        $ ls -ls
        total 8
        drwxr-xr-x  5 damien  staff   160B Jul 25 16:37 group_vars
        drwxr-xr-x  4 damien  staff   128B Jul 25 16:37 host_vars
        -rw-r--r--  1 damien  staff    69B Jul 25 16:37 inventory.ini
        drwxr-xr-x  4 damien  staff   128B Jul 25 16:37 schema
        $ test-schema ansible -i inventory.ini
        Found 4 hosts in the ansible inventory
        FAIL | [ERROR] 12 is not of type 'string' [HOST] leaf1 [PROPERTY] dns_servers:0:address [SCHEMA] schemas/dns_servers
        FAIL | [ERROR] 12 is not of type 'string' [HOST] leaf2 [PROPERTY] dns_servers:0:address [SCHEMA] schemas/dns_servers
        $ test-schema ansible -i inventory.ini -h leaf1
        Found 4 hosts in the ansible inventory
        FAIL | [ERROR] 12 is not of type 'string' [HOST] leaf1 [PROPERTY] dns_servers:0:address [SCHEMA] schemas/dns_servers
        $ test-schema ansible -i inventory.ini -h spine1 --show-pass
        WARNING | Could not find pyproject.toml in the current working directory.
        WARNING | Script is being executed from CWD: /Users/damien/projects/schema_validator/examples/ansible
        WARNING | Using built-in defaults for [tool.schema_validator]
        WARNING | [tool.schema_validator.data_file_to_schema_ids_mapping] is not defined, instances must be tagged to apply schemas to instances
        Found 4 hosts in the inventory
        PASS | [HOST] spine1 | [VAR] dns_servers | [SCHEMA] schemas/dns_servers
        PASS | [HOST] spine1 | [VAR] interfaces | [SCHEMA] schemas/interfaces
        ALL SCHEMA VALIDATION CHECKS PASSED
    """
    if inventory:
        config.load(config_data={"ansible_inventory": inventory})
    else:
        config.load()

    # ---------------------------------------------------------------------
    # Load Schema(s) from disk
    # ---------------------------------------------------------------------
    smgr = SchemaManager(config=config.SETTINGS)

    if not smgr.schemas:
        error("No schemas were loaded")
        sys.exit(1)

    # ---------------------------------------------------------------------
    # Load Ansible Inventory file
    #  - generate hostvar for all devices in the inventory
    #  - Validate Each key in the hostvar individually against the schemas defined in the var jsonschema_mapping
    # ---------------------------------------------------------------------
    inv = AnsibleInventory(inventory=config.SETTINGS.ansible_inventory)
    hosts = inv.get_hosts_containing()
    print(f"Found {len(hosts)} hosts in the inventory")

    error_exists = False

    for host in hosts:
        if limit and host.name != limit:
            continue

        # Generate host_var and automatically remove all keys inserted by ansible
        hostvar = inv.get_clean_host_vars(host)

        # if jsonschema_mapping variable is defined, used it to determine which schema to use to validate each key
        # if jsonschema_mapping is not defined, validate each key in the inventory agains all schemas in the SchemaManager
        mapping = None
        if "jsonschema_mapping" in hostvar:
            mapping = hostvar["jsonschema_mapping"]
            del hostvar["jsonschema_mapping"]

        applicable_schemas = {}

        error_exists = False
        for key, value in hostvar.items():
            if mapping and key in mapping.keys():
                applicable_schemas = {schema_id: smgr.schemas[schema_id] for schema_id in mapping[key]}
            else:
                applicable_schemas = smgr.schemas

            for _, schema_obj in applicable_schemas.items():
                for result in schema_obj.validate({key: value}):

                    result.instance_type = "VAR"
                    result.instance_name = key
                    result.instance_location = host.name

                    if not result.passed():
                        error_exists = True
                        result.print()

                    elif result.passed() and show_pass:
                        result.print()

    if not error_exists:
        print(colored("ALL SCHEMA VALIDATION CHECKS PASSED", "green"))
    else:
        sys.exit(1)
