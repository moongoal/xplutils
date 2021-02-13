#!/usr/bin/env python3

from os.path import basename
import sys
import os
import stat
import logging

from typing import List, Tuple
from configparser import ConfigParser
from pprint import PrettyPrinter

DEFAULT_CONFIG_FILE = 'spbuilder.ini'

SEC_SCENERY = 'scenery'
OPT_SCENERY_LIBS = 'libraries'
OPT_SCENERY_MESHES = 'base'
OPT_SCENERY_DEFAULT_AIRPORTS = 'default_airports'
OPT_SCENERY_CUSTOM_AIRPORTS = 'custom_airports'
OPT_SCENERY_TOP = 'top'

SEC_XPL = 'xplane'
OPT_XPL_INSTALL_PATH = 'install_path'
OPT_XPL_SCEN_INI = 'scenery_packs'

SEC_OPS = 'ops'
OPT_OPS_MERGE = 'merge_mode'
OPT_OPS_ZZEND = 'zz_at_end'

HEADER = """I
1000 Version
SCENERY

"""

logger = logging.getLogger('scenery-ini-builder')


def init_logging():
    """Initialise logging."""
    logger.setLevel(logging.WARNING)
    logger.addHandler(logging.StreamHandler())


def pformat(data) -> str:
    """Pretty-format some data.

    Arguments:
        data -- The data to pretty-format.
    """
    return PrettyPrinter().pformat(data)


def read_config(path: str) -> ConfigParser:
    """Read the config file.

    Arguments:
        path -- Path to the config file.
    """
    parser = ConfigParser()

    logger.info('Reading config file %s' % path)

    with open(path) as f:
        parser.read_file(f)

    return parser


def read_scenery_list(path: str) -> List[str]:
    """Read a list file from the DB.

    Arguments:
        path -- Path to the file to read.
    """
    logger.info('Reading scenery list %s' % path)

    with open(path) as f:
        entries = map(lambda line: line.strip().rstrip('/'), f.readlines())

    return list(entries)


def read_scenery_db(cfg: ConfigParser) -> List[str]:
    """Read the sceneries from the DB.

    Arguments:
        cfg -- The configuration.
    """
    cfg_scen = cfg[SEC_SCENERY]
    scenery_db = []

    for stype in (
        OPT_SCENERY_TOP,
        OPT_SCENERY_CUSTOM_AIRPORTS,
        OPT_SCENERY_DEFAULT_AIRPORTS,
        OPT_SCENERY_LIBS,
        OPT_SCENERY_MESHES
    ):
        if stype in cfg_scen:
            scenery_db.extend(
                read_scenery_list(cfg_scen[stype])
            )

    return scenery_db


def read_xpl_custom_scenery(path: str) -> List[str]:
    """Read sceneries from the custom scenery folder.

    Arguments:
        path -- Path to X-Plane's custom scenery folder.
    """
    sceneries = []

    logger.info('Scanning custom scenery folder %s' % path)

    for centry in os.listdir(path):
        if stat.S_ISDIR(
            os.stat(
                os.path.join(path, centry)
            ).st_mode
        ):
            sceneries.append(
                os.path.join(
                    'Custom Scenery',
                    centry
                )
            ) # NOTE: This logic could be improved to include only sceneries rather than every folder

    return sceneries


def read_all_sceneries(cfg: ConfigParser) -> Tuple[List[str], List[str]]:
    """Read sceneries both from the DB and the custom scenery folder.

    Arguments:
        cfg -- The configuration.

    Return value:
        A tuple (db, scen) where `db` is an ordered list of sceneries from the DB and `scen` is the list of sceneries from the
        X-Plane custom scenery folder that are not already included in  `db` - ordered as well.

        Sceneries in `db` are ordered first by scenery type and then alphabetically. Sceneries in `scen` are ordered alphabetically.
    """
    custom_scenery_folder = os.path.join(cfg[SEC_XPL][OPT_XPL_INSTALL_PATH], 'Custom Scenery')

    cscen = read_xpl_custom_scenery(custom_scenery_folder)
    dscen = read_scenery_db(cfg)
    dscen_base = frozenset(map(os.path.basename, dscen))

    cscen = sorted(
        x for x in cscen if os.path.basename(x) not in dscen_base
    )

    logger.debug('Sceneries loaded from DB: %s', pformat(dscen))
    logger.debug('Sceneries loaded from custom scenery folder: %s', pformat(cscen))

    return dscen, cscen


def make_scenery_ini(cfg: ConfigParser, db_sceneries: List[str], cs_sceneries: List[str]) -> str:
    """Make a string containing the generated scenery_pack.ini file.

    Arguments:
        cfg -- The configuration.
        db_sceneries -- List of sceneries loaded from the DB.
        cs_sceneries -- List of sceneries loaded from the custom scenery folder.
    """
    cfg_ops = cfg[SEC_OPS]
    merge_mode = cfg_ops[OPT_OPS_MERGE]
    zz_at_end = cfg_ops.getboolean(OPT_OPS_ZZEND, fallback=True)
    zz_sceneries = []

    logger.debug('unknown sceneries will be added at the %s of the file' % ('top' if merge_mode == 'top' else 'bottom'))
    logger.debug('zz-sceneries will be added at the %s of the file' % ('bottom' if zz_at_end else 'top'))

    if zz_at_end:
        zz_sceneries = list(filter(lambda s: os.path.basename(s).startswith(('z', '-z')), cs_sceneries))
        cs_sceneries = list(filter(lambda s: s not in zz_sceneries, cs_sceneries))

    sceneries = (cs_sceneries + db_sceneries) if merge_mode == 'top' else (db_sceneries + cs_sceneries)
    sceneries += zz_sceneries
    lines = [
        'SCENERY_{scen_mode} {scen_path}'.format(
            scen_mode='PACK' if s[0] != '-' else 'DISABLED',
            scen_path=(s if s[0] != '-' else s[1:]).replace('\\', '/') + '/'
        ) for s in sceneries
    ]

    return HEADER + '\n'.join(lines)


def write_scenery_ini(cfg: ConfigParser, sini: str):
    """Write the scenery_pack.ini file.

    Arguments:
        cfg -- The configuration.
        sini -- The contents of the ini file.
    """
    cfg_xpl = cfg[SEC_XPL]
    scen_ini_file = cfg_xpl[OPT_XPL_SCEN_INI] \
        if OPT_XPL_SCEN_INI in cfg_xpl \
        else os.path.join(cfg_xpl[OPT_XPL_INSTALL_PATH], 'Custom Scenery', 'scenery_packs.ini')

    with open(scen_ini_file, 'w') as f:
        f.write(sini)


def rebuild_scenery_ini(cfg: ConfigParser):
    """Rebuild the scenery_pack.ini file.

    Arguments:
        cfg -- The configuration.
    """
    write_scenery_ini(
        cfg,
        make_scenery_ini(
            cfg,
            *read_all_sceneries(cfg)
        )
    )


def main(args: List[str]):
    config_file = args[1] if len(args) >= 2 else DEFAULT_CONFIG_FILE

    init_logging()
    config = read_config(config_file)
    rebuild_scenery_ini(config)


if __name__ == '__main__':
    main(sys.argv)
