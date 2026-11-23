// Modo admin (ADR 0015). La sesión va en una cookie HttpOnly que pone y quita el servidor.
import { enviarJson, pedirJson } from './cliente.js'

export const verSesion = () => pedirJson('/api/admin/sesion')
export const entrar = (clave) => enviarJson('/api/admin/sesion', 'POST', { clave })
export const salir = () => fetch('/api/admin/sesion', { method: 'DELETE' })
export const verEstado = () => pedirJson('/api/admin/estado')
export const verRegistros = (nivel = '') => pedirJson(`/api/admin/registros${nivel ? `?nivel=${nivel}` : ''}`)
export const borrarNecesidad = (id, codigo) => enviarJson(`/api/admin/necesidades/${id}/borrado`, 'POST', { codigo })
// `estado`: el que tiene ahora; si ya no lo es (otro «deshacer» a la vez), el servidor responde 409.
export const deshacerPaso = (id, estado) => enviarJson(`/api/admin/necesidades/${id}/deshacer`, 'POST', { estado })
export const corregirNecesidad = (id, cambios) => enviarJson(`/api/admin/necesidades/${id}`, 'PATCH', cambios)
export const lanzarTarea = (nombre, prueba) => enviarJson(`/api/admin/tareas/${nombre}`, 'POST', { prueba })
