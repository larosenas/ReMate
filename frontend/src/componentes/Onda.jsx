// Onda decorativa (degradado de petróleo oscuro a verde claro). Según la guía de estilo, solo en
// la página de inicio, nunca sobre formularios ni tablas.
export default function Onda() {
  return (
    <svg className="pointer-events-none block h-16 w-full md:h-24" viewBox="0 0 1440 120" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="onda-marca" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="var(--color-marca-acento-oscuro)" />
          <stop offset="1" stopColor="var(--color-marca-acento-claro)" />
        </linearGradient>
      </defs>
      <path d="M0 70 C 240 10, 480 10, 720 60 S 1200 120, 1440 40 L 1440 120 L 0 120 Z" fill="url(#onda-marca)" />
    </svg>
  )
}
