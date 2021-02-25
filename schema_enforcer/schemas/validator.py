"""Classes for custom validator plugins."""
# pylint: disable=no-member, too-few-public-methods
import pkgutil
import inspect
from typing import Iterable
import jmespath
from schema_enforcer.validation import ValidationResult


class BaseValidation:
    """Base class for Validation classes."""

    def __init__(self):
        self._results = []

    def add_validation_error(self, message):
        self._results.append(ValidationResult(result="FAIL", schema_id=self.id, message=message))

    def add_validation_pass(self):
        self._results.append(ValidationResult(result="PASS", schema_id=self.id))

    def get_results(self):
        """Return all validation results for this validator."""
        if not self._results:
            self._results.append(ValidationResult(result="PASS", schema_id=self.id))

        return self._results

    def clear_results(self):
        self._results = []

    def validate(self, data: dict, strict: bool):
        """Required function for custom validator."""
        raise NotImplementedError


class JmesPathModelValidation(BaseValidation):
    """Base class for JmesPathModelValidation classes."""

    def validate(self, data: dict, strict: bool):  # pylint: disable=W0613
        """Validate data using custom jmespath validator plugin."""
        operators = {
            "gt": lambda r, v: int(r) > int(v),
            "gte": lambda r, v: int(r) >= int(v),
            "eq": lambda r, v: r == v,
            "lt": lambda r, v: int(r) < int(v),
            "lte": lambda r, v: int(r) <= int(v),
            "contains": lambda r, v: v in r,
        }
        lhs = jmespath.search(self.left, data)
        valid = True
        if lhs:
            # Check rhs for compiled jmespath expression
            if isinstance(self.right, jmespath.parser.ParsedResult):
                rhs = self.right.search(data)
            else:
                rhs = self.right
            valid = operators[self.operator](lhs, rhs)
        if not valid:
            self.add_validation_error(self.error)


def is_validator(obj) -> bool:
    """Returns True if the object is a BaseValidation or JmesPathModelValidation subclass."""
    try:
        return issubclass(obj, BaseValidation) and obj not in (JmesPathModelValidation, BaseValidation)
    except TypeError:
        return False


def load_validators(validator_path: str) -> Iterable[BaseValidation]:
    """Load all validator plugins from validator_path."""
    validators = dict()
    for importer, module_name, _ in pkgutil.iter_modules([validator_path]):
        module = importer.find_module(module_name).load_module(module_name)
        for name, cls in inspect.getmembers(module, is_validator):
            # Default to class name if id doesn't exist
            if not hasattr(cls, "id"):
                cls.id = name
            if cls.id in validators:
                print(f"Duplicate validator name: {cls.id}")
            else:
                validators[cls.id] = cls()
    return validators
