// Enlace (ADR 0014) para descargar un archivo o, si se borró por antigüedad, el aviso en su
// lugar (la descarga respondería 410). `archivo`: el adjunto de la API, con `caducado`.
export default function EnlaceArchivo({ archivo, href, className, children }) {
  if (archivo?.caducado) {
    return (
      <span className="text-slate-500">
        {children} (eliminado por antigüedad: búscalo en Outlook o en SAP)
      </span>
    )
  }
  return (
    <a className={className} href={href}>
      {children}
    </a>
  )
}
