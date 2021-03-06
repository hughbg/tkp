"""

Module that checks the database for source associations


If the database is not available or the database module cannot be
imported, functions will silently return None.
"""

from tkp.db.database import Database
from tkp.db.general import match_nearests_in_catalogs


def match_catalogs(transient):
    """Match transient source with nearest catalog source

    Iterate through available catalogs, and return the nearest source
    for each catalog. Each such source is a dictionary with keys
    catsrcid, catsrcname, catid, catname, ra, decl, ra_err, decl_err,
    dist_arcsec, assoc_r. See
    :py:func:`~tkp.db.utils.match_nearests_in_catalogs` for details.

    The returned dictionary contains the catalog name as its key, and
    a source as the corresponding value.
    """
    # Hardcode the catalogs for now
    #catalogs = {3: 'NVSS', 4: 'VLSS', 5: 'WENSS', 6: 'WENSS'}
    # We check for all catalogs in the db (VLSS, WENSSm, WENSSp, NVSS, EXO)
    database = Database()
    results = {}
    #for key, value in catalogs.iteritems():
    #    results[value] = match_nearests_in_catalogs(
    #        database.connection, transient.srcid,
    #        radius=1, catalogid=key, assoc_r=.1)
    #    if len(results[value]) > 0:
    #        results[value] = results[value][0]
    #    else:
    #        results[value] = {}
    results = match_nearests_in_catalogs(transient['runcat'],
                                    radius=0.5, deRuiter_r=3.717)
    if len(results) > 0:
        results = results[0]
    else:
        results = {}
    return results
