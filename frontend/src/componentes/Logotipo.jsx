// Logotipo de ReMate: una tuerca hexagonal (la pieza de repuesto por excelencia) con un punto
// ámbar y el nombre al lado. Es SVG y texto: no depende de imágenes ni de fuentes externas.
export default function Logotipo({ className = '' }) {
  return (
    <span className={`flex items-center gap-2.5 ${className}`}>
      <svg viewBox="0 0 32 32" className="size-8 shrink-0" aria-hidden="true">
        <path
          d="M16 2.5 27.7 9.25v13.5L16 29.5 4.3 22.75V9.25Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        <circle cx="16" cy="16" r="5.5" fill="none" stroke="var(--color-marca-acento-claro)" strokeWidth="2.5" />
        <circle cx="24.5" cy="7.5" r="3" fill="var(--color-marca-ambar)" />
      </svg>
      <span className="text-xl font-semibold tracking-tight">
        Re<span className="font-normal text-white/80">Mate</span>
      </span>
    </span>
  )
}
