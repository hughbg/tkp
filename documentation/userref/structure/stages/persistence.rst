.. _stage-persistence:

+++++++++++
Persistence
+++++++++++

A record of all images to be processed is made in the database. Within the
database, images are sorted into :ref:`datasets <dataset>`, which group
related images together for processing: searches for transients are performed
between images in a single databset, for instance. All images being processed
are added to the same dataset.

Optionally, a copy of the image pixel data may be stored to a :ref:`MongoDB
<mongodb-intro>` instance at the same time. This is configured in
the :ref:`image_cache section <pipeline_cfg_image_cache>` of the pipeline config.

The following parameters may be configured in the :ref:`job configuration file
<job_params_cfg>`:

Section ``persistence``
-----------------------

``dataset_id``
   Integer. Specifies the unique ID of a dataset to which the current pipeline
   run should be appended. If ``-1``, a new dataset is created. If you specify
   a specific data set ID the configuration of your job is retrieved from the
   database. This will override your job configuration.

``description``
   String. The name under which the database will be stored in the database.
   This value is only used if a new dataset is constructed (see
   ``dataset_id``, below).

