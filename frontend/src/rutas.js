// Los id de la dirección (/necesidades/:id…) solo pueden ser números: así no se meten tal cual
// en las rutas de la API (por ejemplo, «..%2Fproveedores%2F3»).
export const esId = (id) => /^\d+$/.test(id ?? '')
