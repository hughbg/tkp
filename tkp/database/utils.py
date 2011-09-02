# -*- coding: utf-8 -*-

#
# LOFAR Transients Key Project
#

# Local tkp_lib functionality
import monetdb.sql as db
import logging
from tkp.config import config
from tkp.sourcefinder.extract import Detection


DERUITER_R = config['source_association']['deruiter_radius']

def insert_dataset(conn, description):
    """Insert dataset with discription as given by argument.
    DB function insertDataset() sets default values.
    """

    newdsid = None
    try:
        cursor = conn.cursor()
        query = """\
        SELECT insertDataset(%s)
        """
        cursor.execute(query, (description,))
        newdsid = cursor.fetchone()[0]
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query: %s." % query)
        raise
    finally:
        conn.cursor().close()
    return newdsid

def insert_image(conn, dsid, data):
    """Insert an image for a given dataset with the column values
    set in data discriptor
    """

    newimgid = None
    try:
        cursor = conn.cursor()
        query = """\
        SELECT insertImage(%s, %s, %s, %s, %s)
        """
        cursor.execute(query, (dsid
                              ,data.get('freq_eff')
                              ,data.get('freq_bw')
                              ,data.get('taustart_ts')
                              ,data.get('url')
                              ))
        newimgid = cursor.fetchone()[0]
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query: %s." % query)
        raise
    finally:
        cursor.close()
    return newimgid

def load_LSM(ira_min, ira_max, idecl_min, idecl_max, cn1, cn2, cn3, conn):
    raise NotImplementedError

    ##try:
    ##    cursor = conn.cursor()
    ##    procLoadLSM = "CALL LoadLSM(%s,%s,%s,%s,%s,%s,%s)" % (
    ##            ira_min,ira_max,idecl_min,idecl_max,cn1,cn2,cn3)
    ##    cursor.execute(procLoadLSM)
    ##except db.Error, e:
    ##    logging.warn("Failed to insert lsm by procedure LoadLSM")
    ##    raise
    ##finally:
    ##    cursor.close()
    ##conn.commit()


def _empty_detections(conn):
    """Empty the detections table

    Initialize the detections table by
    deleting all entries.

    It is used at the beginning and the end.
    """

    try:
        cursor = conn.cursor()
        query = """\
        DELETE FROM detections
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_into_detections(conn, results):
    """Insert all detections

    Insert all detections, as they are,
    straight into the detection table.

    """

    # TODO: COPY INTO is faster.
    if not results:
        return
    try:
        query = [str(det.serialize()) if isinstance(det, Detection) else
                 str(tuple(det)) for det in results]
        query = "INSERT INTO detections VALUES " + ",".join(query)
        conn.cursor().execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        conn.cursor().close()


def _insert_extractedsources(conn, image_id):
    """Insert all extracted sources with their properties

    Insert all detected sources and some derived properties into the
    extractedsources table.

    """

    cursor = conn.cursor()
    try:
        query = """\
        INSERT INTO extractedsources
          (image_id
          ,zone
          ,ra
          ,decl
          ,ra_err
          ,decl_err
          ,x
          ,y
          ,z
          ,det_sigma
          ,I_peak
          ,I_peak_err
          ,I_int
          ,I_int_err
          )
          SELECT %s
                ,CAST(FLOOR(ldecl) AS INTEGER)
                ,lra
                ,ldecl
                ,lra_err * 3600
                ,ldecl_err * 3600
                ,COS(rad(ldecl)) * COS(rad(lra))
                ,COS(rad(ldecl)) * SIN(rad(lra))
                ,SIN(rad(ldecl))
                ,ldet_sigma
                ,lI_peak
                ,lI_peak_err
                ,lI_int
                ,lI_int_err
            FROM detections
        """
        cursor.execute(query, (image_id,))
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def insert_extracted_sources(conn, image_id, results):
    """Insert all extracted sources

    Insert the sources that were detected by the Source Extraction
    procedures into the extractedsources table.

    Therefore, we use a temporary table containing the"raw" detections,
    from which the sources will then be inserted into extractedsourtces.
    """

    _empty_detections(conn)
    _insert_into_detections(conn, results)
    _insert_extractedsources(conn, image_id)
    _empty_detections(conn)


def _empty_temprunningcatalog(conn):
    """Initialize the temporary storage table

    Initialize the temporary table temprunningcatalog which contains
    the current observed sources.
    """

    try:
        cursor = conn.cursor()
        query = """DELETE FROM temprunningcatalog"""
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_temprunningcatalog(conn, image_id, deRuiter_r):
    """Select matched sources

    Here we select the extractedsources that have a positional match
    with the sources in the running catalogue table (runningcatalog)
    and those who have will be inserted into the temporary running
    catalogue table (temprunningcatalog).

    Explanation of some columns used in the SQL query:

    - avg_I_peak := average of I_peak
    - avg_I_peak_sq := average of I_peak^2
    - avg_weight_I_peak := average of weight of I_peak, i.e. 1/error^2
    - avg_weighted_I_peak := average of weighted i_peak,
         i.e. average of I_peak/error^2
    - avg_weighted_I_peak_sq := average of weighted i_peak^2,
         i.e. average of I_peak^2/error^2

    This result set might contain multiple associations (1-n,n-1)
    for a single known source in runningcatalog.

    The n-1 assocs will be treated similar as the 1-1 assocs.
    """

    try:
        cursor = conn.cursor()
        # !!TODO!!: Add columns for previous weighted averaged values,
        # otherwise the assoc_r will be biased.
        query = """\
INSERT INTO temprunningcatalog
  (xtrsrc_id
  ,assoc_xtrsrc_id
  ,ds_id
  ,datapoints
  ,zone
  ,wm_ra
  ,wm_decl
  ,wm_ra_err
  ,wm_decl_err
  ,avg_wra
  ,avg_wdecl
  ,avg_weight_ra
  ,avg_weight_decl
  ,x
  ,y
  ,z
  ,avg_I_peak
  ,avg_I_peak_sq
  ,avg_weight_peak
  ,avg_weighted_I_peak
  ,avg_weighted_I_peak_sq
  )
  SELECT t0.xtrsrc_id
        ,t0.assoc_xtrsrc_id
        ,t0.ds_id
        ,t0.datapoints
        ,CAST(FLOOR(t0.wm_decl/1) AS INTEGER)
        ,t0.wm_ra
        ,t0.wm_decl
        ,t0.wm_ra_err
        ,t0.wm_decl_err
        ,t0.avg_wra
        ,t0.avg_wdecl
        ,t0.avg_weight_ra
        ,t0.avg_weight_decl
        ,COS(rad(t0.wm_decl)) * COS(rad(t0.wm_ra))
        ,COS(rad(t0.wm_decl)) * SIN(rad(t0.wm_ra))
        ,SIN(rad(t0.wm_decl))
        ,t0.avg_I_peak
        ,t0.avg_I_peak_sq
        ,t0.avg_weight_peak
        ,t0.avg_weighted_I_peak
        ,t0.avg_weighted_I_peak_sq
    FROM (SELECT b0.xtrsrc_id as xtrsrc_id
                ,x0.xtrsrcid as assoc_xtrsrc_id
                ,im0.ds_id
                ,b0.datapoints + 1 AS datapoints
                ,((datapoints * b0.avg_wra + x0.ra /
                  (x0.ra_err * x0.ra_err)) / (datapoints + 1))
                 /
                 ((datapoints * b0.avg_weight_ra + 1 /
                   (x0.ra_err * x0.ra_err)) / (datapoints + 1))
                 AS wm_ra
                ,((datapoints * b0.avg_wdecl + x0.decl /
                  (x0.decl_err * x0.decl_err)) / (datapoints + 1))
                 /
                 ((datapoints * b0.avg_weight_decl + 1 /
                   (x0.decl_err * x0.decl_err)) / (datapoints + 1))
                 AS wm_decl
                ,SQRT(1 / ((datapoints + 1) *
                  ((datapoints * b0.avg_weight_ra +
                    1 / (x0.ra_err * x0.ra_err)) / (datapoints + 1))
                          )
                     ) AS wm_ra_err
                ,SQRT(1 / ((datapoints + 1) *
                  ((datapoints * b0.avg_weight_decl +
                    1 / (x0.decl_err * x0.decl_err)) / (datapoints + 1))
                          )
                     ) AS wm_decl_err
                ,(datapoints * b0.avg_wra + x0.ra / (x0.ra_err * x0.ra_err))
                 / (datapoints + 1) AS avg_wra
                ,(datapoints * b0.avg_wdecl + x0.decl /
                  (x0.decl_err * x0.decl_err))
                 / (datapoints + 1) AS avg_wdecl
                ,(datapoints * b0.avg_weight_ra + 1 /
                  (x0.ra_err * x0.ra_err))
                 / (datapoints + 1) AS avg_weight_ra
                ,(datapoints * b0.avg_weight_decl + 1 /
                  (x0.decl_err * x0.decl_err))
                 / (datapoints + 1) AS avg_weight_decl
                ,(datapoints * b0.avg_I_peak + x0.I_peak)
                 / (datapoints + 1)
                 AS avg_I_peak
                ,(datapoints * b0.avg_I_peak_sq +
                  x0.I_peak * x0.I_peak)
                 / (datapoints + 1)
                 AS avg_I_peak_sq
                ,(datapoints * b0.avg_weight_peak + 1 /
                  (x0.I_peak_err * x0.I_peak_err))
                 / (datapoints + 1)
                 AS avg_weight_peak
                ,(datapoints * b0.avg_weighted_I_peak + x0.I_peak /
                  (x0.I_peak_err * x0.I_peak_err))
                 / (datapoints + 1)
                 AS avg_weighted_I_peak
                ,(datapoints * b0.avg_weighted_I_peak_sq
                  + (x0.I_peak * x0.I_peak) /
                     (x0.I_peak_err * x0.I_peak_err))
                 / (datapoints + 1) AS avg_weighted_I_peak_sq
            FROM runningcatalog b0
                ,extractedsources x0
                ,images im0
           WHERE x0.image_id = %s
             AND x0.image_id = im0.imageid
             AND im0.ds_id = b0.ds_id
             AND b0.zone BETWEEN CAST(FLOOR(x0.decl - 0.025) as INTEGER)
                             AND CAST(FLOOR(x0.decl + 0.025) as INTEGER)
             AND b0.wm_decl BETWEEN x0.decl - 0.025
                                AND x0.decl + 0.025
             AND b0.wm_ra BETWEEN x0.ra - alpha(0.025,x0.decl)
                              AND x0.ra + alpha(0.025,x0.decl)
             AND SQRT(  (x0.ra * COS(rad(x0.decl)) - b0.wm_ra * COS(rad(b0.wm_decl)))
                      * (x0.ra * COS(rad(x0.decl)) - b0.wm_ra * COS(rad(b0.wm_decl)))
                      / (x0.ra_err * x0.ra_err + b0.wm_ra_err * b0.wm_ra_err)
                     + (x0.decl - b0.wm_decl) * (x0.decl - b0.wm_decl)
                      / (x0.decl_err * x0.decl_err + b0.wm_decl_err * b0.wm_decl_err)
                     ) < %s
         ) t0
"""
        cursor.execute(query, (image_id, deRuiter_r))
        #if image_id == 2:
        #    raise
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _flag_multiple_counterparts_in_runningcatalog(conn):
    """Flag source with multiple associations

    Before we continue, we first take care of the sources that have
    multiple associations in both directions.

    -1- running-catalogue sources  <- extracted source

    An extracted source has multiple counterparts in the running
    catalogue.  We only keep the ones with the lowest deRuiter_r
    value, the rest we throw away.

    NOTE:

    It is worth considering whether this might be changed to selecting
    the brightest neighbour source, instead of just the closest
    neighbour.

    (There are case [when flux_lim > 10Jy] that the nearest source has
    a lower flux level, causing unexpected spectral indices)
    """

    try:
        cursor = conn.cursor()
        query = """\
        SELECT t1.xtrsrc_id
              ,t1.assoc_xtrsrc_id
          FROM (SELECT tb0.assoc_xtrsrc_id
                      ,MIN(SQRT((x0.ra - b0.wm_ra) * COS(rad(x0.decl))
                                * (x0.ra - b0.wm_ra) * COS(rad(x0.decl))
                                / (x0.ra_err * x0.ra_err + b0.wm_ra_err *
                                   b0.wm_ra_err)
                               + (x0.decl - b0.wm_decl) *
                                 (x0.decl - b0.wm_decl)
                                / (x0.decl_err * x0.decl_err +
                                   b0.wm_decl_err * b0.wm_decl_err)
                               )
                          ) AS min_r1
                  FROM temprunningcatalog tb0
                      ,runningcatalog b0
                      ,extractedsources x0
                 WHERE tb0.assoc_xtrsrc_id IN (SELECT assoc_xtrsrc_id
                                                 FROM temprunningcatalog
                                               GROUP BY assoc_xtrsrc_id
                                               HAVING COUNT(*) > 1
                                              )
                   AND tb0.xtrsrc_id = b0.xtrsrc_id
                   AND tb0.assoc_xtrsrc_id = x0.xtrsrcid
                GROUP BY tb0.assoc_xtrsrc_id
               ) t0
              ,(SELECT tb1.xtrsrc_id
                      ,tb1.assoc_xtrsrc_id
                      ,SQRT( (x1.ra - b1.wm_ra) * COS(rad(x1.decl))
                            *(x1.ra - b1.wm_ra) * COS(rad(x1.decl))
                            / (x1.ra_err * x1.ra_err +
                               b1.wm_ra_err * b1.wm_ra_err)
                           + (x1.decl - b1.wm_decl) * (x1.decl - b1.wm_decl)
                             / (x1.decl_err * x1.decl_err + b1.wm_decl_err *
                                b1.wm_decl_err)
                           ) AS r1
                  FROM temprunningcatalog tb1
                      ,runningcatalog b1
                      ,extractedsources x1
                 WHERE tb1.assoc_xtrsrc_id IN (SELECT assoc_xtrsrc_id
                                                 FROM temprunningcatalog
                                               GROUP BY assoc_xtrsrc_id
                                               HAVING COUNT(*) > 1
                                              )
                   AND tb1.xtrsrc_id = b1.xtrsrc_id
                   AND tb1.assoc_xtrsrc_id = x1.xtrsrcid
               ) t1
         WHERE t1.assoc_xtrsrc_id = t0.assoc_xtrsrc_id
           AND t1.r1 > t0.min_r1
        """
        cursor.execute(query)
        results = zip(*cursor.fetchall())
        if len(results) != 0:
            xtrsrc_id = results[0]
            assoc_xtrsrc_id = results[1]
            # TODO: Consider setting row to inactive instead of deleting
            query = """\
            DELETE
              FROM temprunningcatalog
             WHERE xtrsrc_id = %s
               AND assoc_xtrsrc_id = %s
            """
            for j in range(len(xtrsrc_id)):
                cursor.execute(query, (xtrsrc_id[j], assoc_xtrsrc_id[j]))
            conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_multiple_assocs(conn):
    """Insert sources with multiple associations

    -2- Now, we take care of the sources in the running catalogue that
    have more than one counterpart among the extracted sources.

    We now make two entries in the running catalogue, in stead of the
    one we had before. Therefore, we 'swap' the ids.
    """

    try:
        cursor = conn.cursor()
        query = """\
        INSERT INTO assocxtrsources
          (xtrsrc_id
          ,assoc_xtrsrc_id
          ,assoc_distance_arcsec
          ,assoc_r
          ,assoc_lr_method
          )
          SELECT t.assoc_xtrsrc_id
                ,t.xtrsrc_id
                ,3600 * deg(2 * ASIN(SQRT((r.x - x.x) * (r.x - x.x)
                                          + (r.y - x.y) * (r.y - x.y)
                                          + (r.z - x.z) * (r.z - x.z)
                                          ) / 2) ) AS assoc_distance_arcsec
                ,3600 * sqrt(
                    ( (r.wm_ra * cos(rad(r.wm_decl)) - x.ra * cos(rad(x.decl)))
                     *(r.wm_ra * cos(rad(r.wm_decl)) - x.ra * cos(rad(x.decl)))
                    ) 
                    / (r.wm_ra_err * r.wm_ra_err + x.ra_err * x.ra_err)
                    + ((r.wm_decl - x.decl) * (r.wm_decl - x.decl)) 
                    / (r.wm_decl_err * r.wm_decl_err + x.decl_err * x.decl_err)
                            ) as assoc_r
                ,1
            FROM temprunningcatalog t
                ,runningcatalog r
                ,extractedsources x
           WHERE t.xtrsrc_id = r.xtrsrc_id
             AND t.xtrsrc_id = x.xtrsrcid
             AND t.xtrsrc_id IN (SELECT xtrsrc_id
                                   FROM temprunningcatalog
                                 GROUP BY xtrsrc_id
                                 HAVING COUNT(*) > 1
                                )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_first_of_assocs(conn):
    """Insert identical ids

    -3- And, we have to insert identical ids to identify a light-curve
    starting point.
    """

    try:
        cursor = conn.cursor()
        query = """\
        INSERT INTO assocxtrsources
          (xtrsrc_id
          ,assoc_xtrsrc_id
          ,assoc_distance_arcsec
          ,assoc_r
          ,assoc_lr_method
          )
          SELECT assoc_xtrsrc_id
                ,assoc_xtrsrc_id
                ,0
                ,0
                ,2
            FROM temprunningcatalog
           WHERE xtrsrc_id IN (SELECT xtrsrc_id
                                 FROM temprunningcatalog
                               GROUP BY xtrsrc_id
                               HAVING COUNT(*) > 1
                              )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _flag_swapped_assocs(conn):
    """Throw away swapped ids

    -4- And, we throw away the swapped id.

    It might be better to flag this record: consider setting rows to
    inactive instead of deleting
    """
    try:
        cursor = conn.cursor()
        query = """\
        DELETE
          FROM assocxtrsources
         WHERE xtrsrc_id IN (SELECT xtrsrc_id
                               FROM temprunningcatalog
                             GROUP BY xtrsrc_id
                             HAVING COUNT(*) > 1
                            )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_multiple_assocs_runcat(conn):
    """Insert new ids of the sources in the running catalogue"""

    try:
        cursor = conn.cursor()
        query = """\
        INSERT INTO runningcatalog
          (xtrsrc_id
          ,ds_id
          ,datapoints
          ,zone
          ,wm_ra
          ,wm_decl
          ,wm_ra_err
          ,wm_decl_err
          ,avg_wra
          ,avg_wdecl
          ,avg_weight_ra
          ,avg_weight_decl
          ,x
          ,y
          ,z
          ,avg_I_peak
          ,avg_I_peak_sq
          ,avg_weight_peak
          ,avg_weighted_I_peak
          ,avg_weighted_I_peak_sq
          )
          SELECT assoc_xtrsrc_id
                ,ds_id
                ,datapoints
                ,zone
                ,wm_ra
                ,wm_decl
                ,wm_ra_err
                ,wm_decl_err
                ,avg_wra
                ,avg_wdecl
                ,avg_weight_ra
                ,avg_weight_decl
                ,x
                ,y
                ,z
                ,avg_I_peak
                ,avg_I_peak_sq
                ,avg_weight_peak
                ,avg_weighted_I_peak
                ,avg_weighted_I_peak_sq
            FROM temprunningcatalog
           WHERE xtrsrc_id IN (SELECT xtrsrc_id
                                 FROM temprunningcatalog
                               GROUP BY xtrsrc_id
                               HAVING COUNT(*) > 1
                              )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _flag_old_assocs_runcat(conn):
    """Here the old assocs in runcat will be deleted."""

    # TODO: Consider setting row to inactive instead of deleting
    try:
        cursor = conn.cursor()
        query = """\
        DELETE
          FROM runningcatalog
         WHERE xtrsrc_id IN (SELECT xtrsrc_id
                               FROM temprunningcatalog
                             GROUP BY xtrsrc_id
                             HAVING COUNT(*) > 1
                            )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _flag_multiple_assocs(conn):
    """Delete the multiple assocs from the temporary running catalogue table"""

    try:
        cursor = conn.cursor()
        query = """\
        DELETE
          FROM temprunningcatalog
         WHERE xtrsrc_id IN (SELECT xtrsrc_id
                               FROM temprunningcatalog
                             GROUP BY xtrsrc_id
                             HAVING COUNT(*) > 1
                            )
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_single_assocs(conn):
    """Insert remaining 1-1 associations into assocxtrsources table"""
    #TODO: check whether last row (t.xtrsrc_id = x.xtrsrcid) should be
    #      t.assocxtrsrc_id = ...)
    try:
        cursor = conn.cursor()
        query = """\
        INSERT INTO assocxtrsources
          (xtrsrc_id
          ,assoc_xtrsrc_id
          ,assoc_distance_arcsec
          ,assoc_r
          ,assoc_lr_method
          )
          SELECT t.xtrsrc_id
                ,t.assoc_xtrsrc_id
                ,3600 * deg(2 * ASIN(SQRT((r.x - x.x) * (r.x - x.x)
                                          + (r.y - x.y) * (r.y - x.y)
                                          + (r.z - x.z) * (r.z - x.z)
                                          ) / 2) ) AS assoc_distance_arcsec
                ,3600 * sqrt(
                    ((r.wm_ra * cos(rad(r.wm_decl)) 
                     - x.ra * cos(rad(x.decl))) 
                    * (r.wm_ra * cos(rad(r.wm_decl)) 
                     - x.ra * cos(rad(x.decl)))) 
                    / (r.wm_ra_err * r.wm_ra_err + x.ra_err*x.ra_err)
                    +
                    ((r.wm_decl - x.decl) * (r.wm_decl - x.decl)) 
                    / (r.wm_decl_err * r.wm_decl_err + x.decl_err*x.decl_err)
                            ) as assoc_r
                ,3
            FROM temprunningcatalog t
                ,runningcatalog r
                ,extractedsources x
           WHERE t.xtrsrc_id = r.xtrsrc_id
             AND t.xtrsrc_id = x.xtrsrcid
        """
        cursor.execute(query)
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _update_runningcatalog(conn):
    """Update the running catalog"""

    try:
        cursor = conn.cursor()
        query = """\
SELECT datapoints
      ,zone
      ,wm_ra
      ,wm_decl
      ,wm_ra_err
      ,wm_decl_err
      ,avg_wra
      ,avg_wdecl
      ,avg_weight_ra
      ,avg_weight_decl
      ,x
      ,y
      ,z
      ,avg_I_peak
      ,avg_I_peak_sq
      ,avg_weight_peak
      ,avg_weighted_I_peak
      ,avg_weighted_I_peak_sq
      ,xtrsrc_id
  FROM temprunningcatalog
        """
        cursor.execute(query)
        results = cursor.fetchall()
        query = """\
UPDATE runningcatalog
  SET datapoints = %s
     ,zone = %s
     ,wm_ra = %s
     ,wm_decl = %s
     ,wm_ra_err = %s
     ,wm_decl_err = %s
     ,avg_wra = %s
     ,avg_wdecl = %s
     ,avg_weight_ra = %s
     ,avg_weight_decl = %s
     ,x = %s
     ,y = %s
     ,z = %s
     ,avg_I_peak = %s
     ,avg_I_peak_sq = %s
     ,avg_weight_peak = %s
     ,avg_weighted_I_peak = %s
     ,avg_weighted_I_peak_sq = %s
WHERE xtrsrc_id = %s
"""
        for result in results:
            cursor.execute(query, tuple(result))
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _count_known_sources(conn, image_id, deRuiter_r):
    """Count number of extracted sources that are know in the running
    catalog"""

    cursor = conn.cursor()
    try:
        query = """\
SELECT COUNT(*)
  FROM extractedsources x0
      ,images im0
      ,runningcatalog b0
 WHERE x0.image_id = %s
   AND x0.image_id = im0.imageid
   AND im0.ds_id = b0.ds_id
   AND b0.zone BETWEEN x0.zone - cast(0.025 as integer)
                   AND x0.zone + cast(0.025 as integer)
   AND b0.wm_decl BETWEEN x0.decl - 0.025
                      AND x0.decl + 0.025
   AND b0.wm_ra BETWEEN x0.ra - alpha(0.025,x0.decl)
                    AND x0.ra + alpha(0.025,x0.decl)
   AND SQRT(  (x0.ra * COS(rad(x0.decl)) - b0.wm_ra * COS(rad(b0.wm_decl)))
            * (x0.ra * COS(rad(x0.decl)) - b0.wm_ra * COS(rad(b0.wm_decl)))
            / (x0.ra_err * x0.ra_err + b0.wm_ra_err * b0.wm_ra_err)
           + (x0.decl - b0.wm_decl) * (x0.decl - b0.wm_decl)
            / (x0.decl_err * x0.decl_err + b0.wm_decl_err * b0.wm_decl_err)
           ) < %s
"""
        cursor.execute(query, (image_id, deRuiter_r))
        y = cursor.fetchall()
        #print "\t\tNumber of known sources (or sources in NOT IN): ", y[0][0]
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_new_assocs(conn, image_id, deRuiter_r):
    """Insert new associations for unknown sources

    This inserts new associations for the sources that were not known
    in the running catalogue (i.e. they did not have an entry in the
    runningcatalog table).
    """

    cursor = conn.cursor()
    try:
        query = """\
        INSERT INTO assocxtrsources
          (xtrsrc_id
          ,assoc_xtrsrc_id
          ,assoc_distance_arcsec
          ,assoc_r
          ,assoc_lr_method
          )
          SELECT x1.xtrsrcid as xtrsrc_id
                ,x1.xtrsrcid as assoc_xtrsrc_id
                ,0
                ,0
                ,4
            FROM extractedsources x1
           WHERE x1.image_id = %s
             AND x1.xtrsrcid NOT IN (
                 SELECT x0.xtrsrcid
                  FROM extractedsources x0
                      ,runningcatalog b0
                      ,images im0
                 WHERE x0.image_id = %s
                   AND x0.image_id = im0.imageid
                   AND im0.ds_id = b0.ds_id
                   AND b0.zone BETWEEN x0.zone - cast(0.025 as integer)
                                   AND x0.zone + cast(0.025 as integer)
                   AND b0.wm_decl BETWEEN x0.decl - 0.025
                                            AND x0.decl + 0.025
                   AND b0.wm_ra BETWEEN x0.ra - alpha(0.025,x0.decl)
                                          AND x0.ra + alpha(0.025,x0.decl)
                   AND SQRT(  (x0.ra * COS(rad(x0.decl)) - b0.wm_ra * COS(rad(b0.wm_decl)))
                            * (x0.ra * COS(rad(x0.decl)) - b0.wm_ra * COS(rad(b0.wm_decl)))
                            / (x0.ra_err * x0.ra_err + b0.wm_ra_err * b0.wm_ra_err)
                           + (x0.decl - b0.wm_decl) * (x0.decl - b0.wm_decl)
                            / (x0.decl_err * x0.decl_err + b0.wm_decl_err * b0.wm_decl_err)
                           ) < %s
                                    )
        """
        cursor.execute(query, (image_id, image_id, deRuiter_r))
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def _insert_new_source_runcat(conn, image_id, deRuiter_r):
    """Insert new sources into the running catalog"""
    # TODO: check zone cast in search radius!
    cursor = conn.cursor()
    try:
        query = """\
INSERT INTO runningcatalog
  (xtrsrc_id
  ,ds_id
  ,datapoints
  ,zone
  ,wm_ra
  ,wm_decl
  ,wm_ra_err
  ,wm_decl_err
  ,avg_wra
  ,avg_wdecl
  ,avg_weight_ra
  ,avg_weight_decl
  ,x
  ,y
  ,z
  ,avg_I_peak
  ,avg_I_peak_sq
  ,avg_weight_peak
  ,avg_weighted_I_peak
  ,avg_weighted_I_peak_sq
  )
  SELECT x1.xtrsrcid
        ,im1.ds_id
        ,1
        ,x1.zone
        ,x1.ra
        ,x1.decl
        ,x1.ra_err
        ,x1.decl_err
        ,x1.ra / (x1.ra_err * x1.ra_err)
        ,x1.decl / (x1.decl_err * x1.decl_err)
        ,1 / (x1.ra_err * x1.ra_err)
        ,1 / (x1.decl_err * x1.decl_err)
        ,x1.x
        ,x1.y
        ,x1.z
        ,I_peak
        ,I_peak * I_peak
        ,1 / (I_peak_err * I_peak_err)
        ,I_peak / (I_peak_err * I_peak_err)
        ,I_peak * I_peak / (I_peak_err * I_peak_err)
    FROM extractedsources x1
        ,images im1
   WHERE x1.image_id = %s
     AND x1.image_id = im1.imageid
     AND x1.xtrsrcid NOT IN (
         SELECT x0.xtrsrcid
          FROM extractedsources x0
              ,runningcatalog b0
              ,images im0
         WHERE x0.image_id = %s
           AND x0.image_id = im0.imageid
           AND im0.ds_id = b0.ds_id
           AND b0.zone BETWEEN x0.zone - cast(0.025 as integer)
                           AND x0.zone + cast(0.025 as integer)
           AND b0.wm_decl BETWEEN x0.decl - 0.025
                                    AND x0.decl + 0.025
           AND b0.wm_ra BETWEEN x0.ra - alpha(0.025,x0.decl)
                                  AND x0.ra + alpha(0.025,x0.decl)
           AND b0.x * x0.x + b0.y * x0.y + b0.z * x0.z > COS(rad(0.025))
           AND SQRT(  (x0.ra * COS(rad(x0.decl)) - b0.wm_ra * COS(rad(b0.wm_decl)))
                    * (x0.ra * COS(rad(x0.decl)) - b0.wm_ra * COS(rad(b0.wm_decl)))
                    / (x0.ra_err * x0.ra_err + b0.wm_ra_err * b0.wm_ra_err)
                   + (x0.decl - b0.wm_decl) * (x0.decl - b0.wm_decl)
                    / (x0.decl_err * x0.decl_err + b0.wm_decl_err * b0.wm_decl_err)
                   ) < %s
           )
"""
        cursor.execute(query, (image_id, image_id, deRuiter_r))
        conn.commit()
    except db.Error, e:
        logging.warn("Failed on query nr %s." % query)
        raise
    finally:
        cursor.close()


def associate_extracted_sources(conn, image_id, deRuiter_r=DERUITER_R):
    """Associate extracted sources with sources detected in the running
    catalog

    The dimensionless distance between two sources is given by the
    "De Ruiter radius", see Ch2&3 of thesis Scheers.

    Here we use a default value of deRuiter_r = 3.717/3600. for a
    reliable association.
    """

    #if image_id == 2:
    #    raise
    _empty_temprunningcatalog(conn)
    _insert_temprunningcatalog(conn, image_id, deRuiter_r)
    _flag_multiple_counterparts_in_runningcatalog(conn)
    _insert_multiple_assocs(conn)
    _insert_first_of_assocs(conn)
    _flag_swapped_assocs(conn)
    _insert_multiple_assocs_runcat(conn)
    _flag_old_assocs_runcat(conn)
    _flag_multiple_assocs(conn)
    #+-----------------------------------------------------+
    #| After all this, we are now left with the 1-1 assocs |
    #+-----------------------------------------------------+
    _insert_single_assocs(conn)
    _update_runningcatalog(conn)
    _empty_temprunningcatalog(conn)
    _count_known_sources(conn, image_id, deRuiter_r)
    _insert_new_assocs(conn, image_id, deRuiter_r)
    _insert_new_source_runcat(conn, image_id, deRuiter_r)


def _select_variability_indices(conn, dsid, V_lim, eta_lim):
    """Select sources and variability indices in the running catalog"""

    results = []
    cursor = conn.cursor()
    try:
        query = """\
SELECT xtrsrc_id
      ,ds_id
      ,datapoints
      ,wm_ra
      ,wm_decl
      ,wm_ra_err
      ,wm_decl_err
      ,sqrt(datapoints*(avg_I_peak_sq - avg_I_peak*avg_I_peak) /
            (datapoints-1)) / avg_I_peak as V
      ,(datapoints/(datapoints-1)) *
       (avg_weighted_I_peak_sq -
        avg_weighted_I_peak * avg_weighted_I_peak / avg_weight_peak)
       as eta
  FROM runningcatalog
 WHERE ds_id = %s
   AND datapoints > 1
   AND (sqrt(datapoints*(avg_I_peak_sq - avg_I_peak*avg_I_peak) /
             (datapoints-1)) / avg_I_peak > %s
        OR (datapoints/(datapoints-1)) *
            (avg_weighted_I_peak_sq -
             avg_weighted_I_peak * avg_weighted_I_peak /
             avg_weight_peak) > %s
       )
"""
        cursor.execute(query, (dsid, V_lim, eta_lim))
        results = cursor.fetchall()
        results = [dict(srcid=x[0], npoints=x[2], v_nu=x[7], eta_nu=x[8])
                   for x in results]
        #conn.commit()
    except db.Error:
        logging.warn("Failed on query %s", query)
        raise
    finally:
        cursor.close()
    return results


def lightcurve(conn, xtrsrcid):
    """Obtain a light curve for a specific source"""

    results = [[]]
    cursor = conn.cursor()
    try:
        query = """\
SELECT im.taustart_ts, im.tau_time, ex.i_peak, ex.i_peak_err, ex.xtrsrcid
FROM extractedsources ex, assocxtrsources ax, images im
WHERE ax.xtrsrc_id IN (
    SELECT xtrsrc_id FROM assocxtrsources WHERE assoc_xtrsrc_id = %s)
  AND ex.xtrsrcid = ax.assoc_xtrsrc_id
  AND ex.image_id = im.imageid
ORDER BY im.taustart_ts"""
        cursor.execute(query, (xtrsrcid,))
        results = cursor.fetchall()
    except db.Error:
        logging.warn("Failed to obtain light curve")
        raise
    finally:
        cursor.close()
    return results

        
def detect_variable_sources(conn, dsid, V_lim, eta_lim):
    """Detect variability in extracted sources compared to the previous
    detections"""

    #sources = _select_variability_indices(conn, dsid, V_lim, eta_lim)
    return _select_variability_indices(conn, dsid, V_lim, eta_lim)


def associate_catalogued_sources_in_area(conn, ra, dec, radius, deRuiter_r=DERUITER_R):
    pass
