// «Otro proveedor» en «Solicitar ofertas» y en «Añadir oferta»: los errores van junto a su campo
// (nombre o correo) y, si no se sabe cuál, debajo del formulario.

export function comprobarProveedorNuevo({ nombre, email }) {
  const errores = {}
  if (!nombre.trim()) errores.nombre = 'Indica el nombre del proveedor.'
  if (!email.trim()) errores.email = 'Indica el correo del proveedor.'
  return errores
}

export function erroresDeProveedorNuevo(error) {
  if (error.codigo === 'correo_duplicado') return { email: error.message }
  const campo = error.detalles?.campo
  if (campo === 'email' || campo === 'nombre') return { [campo]: error.message }
  return { general: error.message }
}
