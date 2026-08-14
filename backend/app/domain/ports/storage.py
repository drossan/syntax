"""app.domain.ports.storage — puerto de almacenamiento de adjuntos.

GUIÓN (→ tarea 10)
------------------
Interfaz (async) para el binario de los ``Attachment`` (03): el fichero **no** vive en Postgres, solo su
metadato + ``storage_key``. Fase 1: adaptador local/filesystem; S3 **diferido** (seam — el puerto lo
permite).

  - ``put(content, filename, content_type) -> storage_key``
  - ``get(storage_key) -> stream`` · ``delete(storage_key)`` (lo invoca el servicio al borrar el mensaje;
    la FK CASCADE de 03 borra la fila, el binario lo limpia el servicio).

Anti-patrón: guardar el binario en la BD; acoplar el dominio a un SDK de S3.
"""
