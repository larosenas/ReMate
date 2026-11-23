// Pide al navegador que descargue un archivo de la API (por ejemplo, el .eml de CU-002).
// Va en un módulo aparte para poder simularlo en las pruebas.
// `nombre`: el nombre del archivo, para los que no vienen de una ruta de la API.
export function descargar(url, nombre = '') {
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  document.body.append(enlace)
  enlace.click()
  enlace.remove()
}
