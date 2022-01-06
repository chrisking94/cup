#!/usr/bin/env python
# encoding: utf-8
#
# Copyright  (c) 2014 deanishe@deanishe.net
#
# MIT Licence. See http://opensource.org/licenses/MIT
#
# Created on 2014-02-24
#

"""Drives Script Filter to show unit conversions in Alfred 3."""

from __future__ import print_function

import logging
import os
import sys

from pint import UnitRegistry, UndefinedUnitError, DimensionalityError

from config import (
    bootstrap,
    DEFAULT_UNIT_DEFINITIONS,
    BUILTIN_UNIT_DEFINITIONS,
    COPY_UNIT,
    CURRENCY_CACHE_AGE,
    CURRENCY_CACHE_NAME,
    CURRENCY_DECIMAL_PLACES,
    CUSTOM_DEFINITIONS_FILENAME,
    DECIMAL_PLACES,
    DECIMAL_SEPARATOR,
    DEFAULT_SETTINGS,
    DYNAMIC_DECIMALS,
    HELP_URL,
    ICON_UPDATE,
    NOKEY_FILENAME,
    OPENX_APP_KEY,
    THOUSANDS_SEPARATOR,
    UPDATE_SETTINGS,
)
from defaults import Defaults
from src.utils import unicode

log = logging.getLogger()

# Pint objects
ureg = UnitRegistry(DEFAULT_UNIT_DEFINITIONS)
ureg.default_format = 'P'
# Q = ureg.Quantity


def unit_is_currency(unit):
    """Return ``True`` if specified unit is a fiat currency."""
    from config import CURRENCIES
    return unit.upper() in CURRENCIES


class NoToUnits(Exception):
    """Raised if there are no to units (or defaults)."""


class Input(object):
    """Parsed user query."""

    def __init__(self, number, dimensionality, from_unit,
                 to_unit=None, context=None):
        """Create new ``Input``."""
        self.number = number
        self.dimensionality = dimensionality
        self.from_unit = from_unit
        self.to_unit = to_unit
        self.context = context

    @property
    def is_currency(self):
        """`True` if Input is a currency."""
        return self.dimensionality == u'[currency]'

    def __repr__(self):
        """Code-like representation of `Input`."""
        return ('Input(number={!r}, dimensionality={!r}, '
                'from_unit={!r}, to_unit={!r})').format(
                    self.number, self.dimensionality, self.from_unit,
                    self.to_unit)

    def __str__(self):
        """Printable representation of `Input`."""
        return self.__repr__()


class Formatter(object):
    """Format a number.

    Attributes:
        decimal_places (int): Number of decimal places in formatted numbers
        decimal_separator (str): Character to use as decimal separator
        thousands_separator (str): Character to use as thousands separator

    """

    def __init__(self, decimal_places=2, decimal_separator='.',
                 thousands_separator='', dynamic_decimals=True):
        """Create a new `Formatter`."""
        self.decimal_places = decimal_places
        self.decimal_separator = decimal_separator
        self.thousands_separator = thousands_separator
        self.dynamic_decimals = dynamic_decimals

    def _decimal_places(self, n):
        """Calculate the number of decimal places the result should have.

        If :attr:`dynamic_decimals` is `True`, increase the number of
        decimal places until the result is non-zero.

        Args:
            n (float): Number that will be formatted.

        Returns:
            int: Number of decimal places for result.

        """
        log.debug('DYNAMIC_DECIMALS: %s', ('off', 'on')[self.dynamic_decimals])

        if not self.dynamic_decimals or n == 0.0:
            return self.decimal_places

        m = max(self.decimal_places, 10) + 1
        p = self.decimal_places
        while p < m:
            e = 10 ** p
            i = n * e
            # log.debug('n=%r, e=%d, i=%r, p=%d', n, e, i, p)
            if n * e >= 10:
                break

            p += 1

        # Remove trailing zeroes
        s = str(i)
        if '.' not in s:  # not a fraction
            return p

        _, s = s.split('.', 1)
        # log.debug('s=%s, p=%d', s, p)
        while s.endswith('0'):
            s = s[:-1]
            p -= 1
            # log.debug('s=%s, p=%d', s, p)

        p = max(p, self.decimal_places)
        log.debug('places=%d', p)
        return p

    def formatted(self, n, unit=None):
        """Format number with thousands and decimal separators."""
        sep = u''
        if self.thousands_separator:
            sep = u','

        fmt = u'{{:0{}.{:d}f}}'.format(sep, self._decimal_places(n))
        num = fmt.format(n)
        # log.debug('n=%r, fmt=%r, num=%r', n, fmt, num)
        num = num.replace(',', '||comma||')
        num = num.replace('.', '||point||')
        num = num.replace('||comma||', self.thousands_separator)
        num = num.replace('||point||', self.decimal_separator)

        if unit:
            num = u'{} {}'.format(num, unit)

        return num

    def formatted_no_thousands(self, n, unit=None):
        """Format number with decimal separator only."""
        fmt = u'{{:0.{:d}f}}'.format(self._decimal_places(n))
        num = fmt.format(n)
        # log.debug('n=%r, fmt=%r, num=%r', n, fmt, num)
        num = num.replace('.', '||point||')
        num = num.replace('||point||', self.decimal_separator)

        if unit:
            num = u'{} {}'.format(num, unit)

        return num


class Conversion(object):
    """Results of a conversion.

    Attributes:
        dimensionality (str): Dimensionality of conversion
        from_number (float): Input
        from_unit (str): Unit of input
        to_number (float): Conversion result
        to_unit (str): Unit of output

    """

    def __init__(self, from_number, from_unit, to_number, to_unit,
                 dimensionality):
        """Create a new `Conversion`."""
        self.from_number = from_number
        self.from_unit = from_unit
        self.to_number = to_number
        self.to_unit = to_unit
        self.dimensionality = dimensionality

    def __str__(self):
        """Pretty string representation."""
        return u'{:f} {} = {:f} {} {}'.format(
            self.from_number, self.from_unit, self.to_number, self.to_unit,
            self.dimensionality).encode('utf-8')

    def __repr__(self):
        """Code-like representation."""
        return ('Conversion(from_number={!r}, from_unit={!r}, '
                'to_number={!r}, to_unit={!r}, dimensionality={!r}').format(
                    self.from_number, self.from_unit, self.to_number,
                    self.to_unit, self.dimensionality)


class Converter(object):
    """Parse query and convert.

    Parses user input into an `Input` object, then converts this into
    one or more `Conversion` objects.

    Attributes:
        decimal_separator (str): Decimal separator character in input.
        defaults (defaults.Defaults): Default units for conversions.
        thousands_separator (str): Thousands separator character in input.

    """

    def __init__(self, defaults, decimal_separator='.',
                 thousands_separator=','):
        """Create new `Converter`.

        Args:
            defaults (defaults.Defaults): Default units for conversions.
            decimal_separator (str, optional): Decimal separator character
                in query.
            thousands_separator (str, optional): Thousands separator character
                in query.

        """
        self.defaults = defaults
        self.decimal_separator = decimal_separator
        self.thousands_separator = thousands_separator

    def convert(self, i):
        """Convert `Input`.

        Args:
            i (Input): Parsed user query

        Returns:
            list: Sequence of `Conversion` objects

        Raises:
            NoToUnits: Raised if user hasn't specified a destination unit
                or there are no default units for the given dimensionality
            ValueError: Raised if a unit is unknown

        """
        if i.to_unit is not None:
            units = [i.to_unit]
        else:
            units = [u for u in self.defaults.defaults(i.dimensionality)
                     if u != i.from_unit]

        if not units:
            raise NoToUnits()

        results = []
        qty = ureg.Quantity(i.number, i.from_unit)
        for u in units:
            try:
                to_unit = ureg.Quantity(1, u)
            except UndefinedUnitError:
                raise ValueError('Unknown unit: {}'.format(u))

            conv = qty.to(to_unit)
            log.debug('[convert] %s -> %s = %s', i.from_unit, u, conv)
            results.append(Conversion(i.number, i.from_unit,
                                      conv.magnitude, u, i.dimensionality))

        return results

    def parse(self, query):
        """Parse user query into `Input`.

        Args:
            query (str): User query

        Returns:
            Input: Parsed query

        Raises:
            ValueError: Raised if query is invalid

        """
        ctx, query = self.parse_context(query)
        qty, tail = self.parse_quantity(query)

        # Show error message for invalid input
        if qty is None:
            if ctx:
                raise ValueError('No quantity')

            raise ValueError('Start your query with a number')

        if not len(tail):
            raise ValueError('No units specified')

        log.debug('[parser] quantity=%s, tail=%s', qty, tail)

        # Parse query into pint.Quantity objects
        from_unit, to_unit = self.parse_units(tail, qty)

        # Create `Input` from parsed query
        tu = None
        if to_unit:
            tu = unicode(to_unit.units)
        i = Input(from_unit.magnitude, unicode(from_unit.dimensionality),
                  unicode(from_unit.units), tu, ctx)

        log.debug('[parser] %s', i)

        return i

    def parse_context(self, query):
        """Extract and set context.

        Args:
            query (str): User input

        Returns:
            (list/str, str): Parsed or empty context and rest of query

        Raises:
            ValueError: Raised if supplied context is invalid

        """
        ctx = []
        for c in query:
            if c in 'abcdefghijklmnopqrstuvwxyz':
                ctx.append(c)
            else:
                break

        if ctx:
            ctx = ''.join(ctx)
            try:
                ureg.enable_contexts(ctx)
            except KeyError:
                raise ValueError('Unknown context: {}'.format(ctx))

            log.debug('[parser] context=%s', ctx)
            query = query[len(ctx):].strip()

        return ctx, query

    def parse_quantity(self, query):
        """Extract quantity from query.

        Args:
            query (str): (Partial) user query

        Returns:
            (float, str): Quantity and remainder of query

        """
        qty = []
        qtychars = ('+-1234567890' + self.thousands_separator +
                    self.decimal_separator)
        for c in query:
            if c in qtychars:
                if c == '+':
                    qty.append('')
                if c == self.thousands_separator:
                    log.debug('ignored thousands separator "%s"', c)
                    # Append an empty string so qty length is correct
                    qty.append('')
                elif c == self.decimal_separator:
                    qty.append('.')
                else:
                    qty.append(c)
            else:
                break
        if not len(qty):
            return None, ''

        tail = query[len(qty):].strip()
        qty = float(''.join(qty))

        return qty, tail

    def parse_units(self, query, qty=1):
        """Extract from and (optional) to units from query.

        Args:
            query (str): (Partial) user input
            qty (int, optional): Quantity of from units

        Returns:
            (pint.Quantity, pint.Quantity): From and to quantities. To
                quantity is initialised with ``1``.

        Raises:
            ValueError: Raised if a unit is unknown, or more than 2 units
                are specified.

        """
        from_unit = to_unit = None
        units = [s.strip() for s in query.split()]
        from_unit = units[0]
        log.debug('[parser] from_unit=%s', from_unit)

        if len(units) > 1:
            to_unit = units[1]
            log.debug('[parser] to_unit=%s', to_unit)
        if len(units) > 2:
            raise ValueError('More than 2 units specified')

        # Validate units
        try:
            from_unit = ureg.Quantity(qty, from_unit)
        except UndefinedUnitError:
            raise ValueError('Unknown unit: ' + from_unit)

        if to_unit:
            try:
                to_unit = ureg.Quantity(1, to_unit)
            except UndefinedUnitError:
                raise ValueError('Unknown unit: ' + to_unit)

        return from_unit, to_unit


def register_units():
    """Add built-in and user units to unit registry."""
    # Add custom units from workflow and user data
    ureg.load_definitions(BUILTIN_UNIT_DEFINITIONS)

    user_definitions = CUSTOM_DEFINITIONS_FILENAME

    # User's custom units
    if os.path.exists(user_definitions):
        ureg.load_definitions(user_definitions)


def register_exchange_rates(exchange_rates):
    """Add currency definitions with exchange rates to unit registry.

    Args:
        exchange_rates (dict): `{symbol: rate}` mapping of currencies.

    """
    # USD will be the baseline currency. All exchange rates are
    # defined relative to the US dollar
    ureg.define('USD = [currency] = usd')

    for abbr, rate in exchange_rates.items():
        definition = '{} = usd / {}'.format(abbr, rate)

        try:
            ureg.Quantity(1, abbr)
        except UndefinedUnitError:
            pass  # Unit does not exist
        else:
            log.debug('skipping currency %s : Unit is already defined', abbr)
            continue

        try:
            ureg.Quantity(1, abbr.lower())
        except UndefinedUnitError:
            definition += ' = {}'.format(abbr.lower())

        log.debug('registering currency : %r', definition)
        ureg.define(definition)


