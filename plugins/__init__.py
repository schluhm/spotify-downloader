import abc
import glob
import os
import attr
import bisect

import click

_plugins = []


@attr.s(hash=True)
class PluginSpecificOption:
    name = attr.ib()
    flag_pattern = attr.ib()
    type = attr.ib(default=None)
    help = attr.ib(default=None)
    default = attr.ib(default=None)
    required = attr.ib(default=True)

    def as_click_option(self, flag):
        if self.required:
            return click.option(
                str(self.name),
                str(self.flag_pattern),
                type=self.type,
                default=self.default,
                help=self.help if self.help is not None else "",
                show_default=True,
                cls=RequiredIf,
                required_if=flag
            )
        else:
            return click.option(
                str(self.name),
                str(self.flag_pattern),
                type=self.type,
                default=self.default,
                help=self.help if self.help is not None else "",
                show_default=True
            )


class RequiredIf(click.Option):
    def __init__(self, *args, **kwargs):
        self.required_if = kwargs.pop('required_if')
        assert self.required_if, "'required_if' parameter required"
        kwargs['help'] = (kwargs.get('help', '') +
                          ' NOTE: This argument is required for %s' %
                          self.required_if
                          ).strip()
        super(RequiredIf, self).__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        we_are_present = self.name in opts
        other_present = self.required_if in opts

        if other_present:
            if not we_are_present:
                raise click.UsageError(
                    "Illegal usage: `%s` is required for `%s`" % (
                        self.name, self.required_if))
            else:
                self.prompt = None

        return super(RequiredIf, self).handle_parse_result(
            ctx, opts, args)


class Plugin:
    @staticmethod
    @abc.abstractmethod
    def get_name():
        """
        Return the name of this plugin.
        """
        pass

    @classmethod
    def get_plugin_specific_options(cls):
        return [
            PluginSpecificOption(
                cls.flag(),
                f"--plugin-{cls.get_name()}/--no-plugin-{cls.get_name()}",
                help=cls.__doc__,
                default=False
            )
        ]

    @classmethod
    def flag(cls):
        return f"enable_{cls.__name__}"

    @classmethod
    def is_plugin_enabled(cls, **kwargs):
        return cls.flag() in kwargs and kwargs[cls.flag()]

    def on_track_done(self, track_path, track_name):
        pass


def list_plugin_specific_options():
    options = []

    for plugin_class in _plugins:
        options += [x.as_click_option(plugin_class.flag()) for x in plugin_class.get_plugin_specific_options()]

    return options


def register(plugin_class):
    bisect.insort(_plugins, plugin_class, key=lambda x: x.get_name())
    return plugin_class


# Quite a hacky plugin system. Just import all python files not starting with __

modules = glob.glob(os.path.join(os.path.dirname(__file__), "*.py"))
__all__ = [os.path.basename(f)[:-3] for f in modules if not f.startswith("__")]

from . import *  # noqa


def get_plugins() -> [Plugin]:
    return _plugins
