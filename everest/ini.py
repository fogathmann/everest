"""
This file is part of the everest project. 
See LICENSE.txt for licensing, CONTRIBUTORS.txt for contributor information.

Created on May 30, 2012.
"""
from ConfigParser import SafeConfigParser
import nose.plugins
import os

__docformat__ = 'reStructuredText en'
__all__ = ['EverestIni',
           'EverestNosePlugin',
           ]


class EverestNosePlugin(nose.plugins.Plugin):
    """
    Nose plugin extension.

    Provides a nose option that configures a test application configuration
    file.
    """
    def __init__(self, *args, **kw):
        nose.plugins.Plugin.__init__(self, *args, **kw)
        self.__opt_name = 'app-ini-file'
        self.__dest_opt_name = self.__opt_name.replace('-', '_')

    def options(self, parser, env=None):
        """Add command-line options for this plugin."""
        if env is None:
            env = os.environ
        env_opt_name = 'NOSE_%s' % self.__dest_opt_name.upper()
        parser.add_option("--%s" % self.__opt_name,
                          dest=self.__dest_opt_name,
                          type="string",
                          default=env.get(env_opt_name),
                          help=".ini file providing the environment for the "
                               "test web application.")

    def configure(self, options, conf):
        """Configure the plugin"""
        super(EverestNosePlugin, self).configure(options, conf)
        opt_val = getattr(options, self.__dest_opt_name, None)
        if opt_val:
            self.enabled = True
            EverestIni.ini_file_path = opt_val


class EverestIni(object):
    """
    Helper class providing access to settings parsed from an ini file.
    
    By default, the ini file configured through the :class:`EverestNosePlugin`
    is used.
    """
    #: Path to the global ini file. Set through the nose plugin.
    ini_file_path = None

    __ini_parser = None

    def __init__(self, ini_file_path=None):
        if ini_file_path is None:
            self.__ini_parser = self.__check_ini_file()
        else:
            self.__ini_parser = self.__make_parser()
            self.__ini_parser.read(ini_file_path)
            self.ini_file_path = ini_file_path

    def get_settings(self, section):
        """
        Returns a dictionary containing the settings for the given ini file
        section.
        
        :param str section: ini file section.
        """
        return dict(self.__ini_parser.items(section))

    def get_setting(self, section, key):
        """
        Returns the specified setting from the given ini file section.
        
        :param str section: ini file section.
        :param str key: key to look up in the section.
        """
        return self.__ini_parser.get(section, key)

    def has_setting(self, section, key):
        """
        Checks if the specified ini file section has a setting with the given
        name.
        """
        return self.__ini_parser.has_option(section, key)

    @classmethod
    def __check_ini_file(cls):
        if cls.ini_file_path is None:
            raise ValueError('You need to set an application '
                             'initialization file path (e.g., through '
                             'the EverestAppNosePlugin).')
        if cls.__ini_parser is None:
            cls.__ini_parser = cls.__make_parser()
            cls.__ini_parser.read(cls.ini_file_path)
        return cls.__ini_parser

    @classmethod
    def __make_parser(cls):
        return SafeConfigParser(
                    defaults={'here':os.path.dirname(cls.ini_file_path)})


