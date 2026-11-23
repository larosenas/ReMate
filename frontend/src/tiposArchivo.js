// CU-004 — Tipo de archivo que la aplicación propone para un adjunto según su extensión.
const EXTENSIONES = {
  pdf: 'pdf',
  xls: 'excel',
  xlsx: 'excel',
  xlsm: 'excel',
  csv: 'excel',
  doc: 'word',
  docx: 'word',
  png: 'imagen',
  jpg: 'imagen',
  jpeg: 'imagen',
  gif: 'imagen',
  bmp: 'imagen',
  tif: 'imagen',
  tiff: 'imagen',
  webp: 'imagen',
}
export function tipoPorExtension(nombre) {
  const extension = nombre.toLowerCase().split('.').pop()
  return EXTENSIONES[extension] ?? 'otro'
}
