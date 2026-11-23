// Cabecera: barra en acero oscuro con el logotipo de ReMate. Los enlaces marcan la página actual
// con un subrayado en el color de acento; el enlace con `destacado` (la acción principal) va como
// botón. En el móvil, los enlaces pasan a una segunda fila que se desplaza en horizontal.
import { Link, NavLink } from 'react-router'
import Logotipo from './Logotipo'

function claseEnlace({ isActive }, destacado) {
  if (destacado) {
    return `rounded bg-marca-acento px-4 py-2 text-white hover:bg-marca-acento-oscuro ${isActive ? 'ring-1 ring-white/40' : ''}`
  }
  return `border-b-2 py-1 transition-colors motion-reduce:transition-none ${
    isActive ? 'border-marca-acento text-white' : 'border-transparent text-white/70 hover:text-white'
  }`
}

export default function Cabecera({ enlaces = [] }) {
  return (
    <header className="bg-marca-oscuro text-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 px-4 sm:px-6 md:h-18 md:flex-nowrap">
        <Link to="/" className="flex h-16 items-center md:h-auto" aria-label="ReMate, ir al panel">
          <Logotipo />
        </Link>
        <nav className="-mx-4 flex w-[calc(100%+2rem)] min-w-0 items-center gap-6 overflow-x-auto border-t border-white/10 px-4 py-3 text-sm whitespace-nowrap md:mx-0 md:ml-auto md:w-auto md:gap-8 md:border-0 md:p-0">
          {enlaces.map((enlace) => (
            // NavLink marca la página actual (aria-current="page") sin recargar la página.
            <NavLink key={enlace.href} to={enlace.href} end className={(estado) => claseEnlace(estado, enlace.destacado)}>
              {enlace.texto}
            </NavLink>
          ))}
        </nav>
      </div>
      {/* Línea fina con el degradado de la onda. */}
      <div className="h-0.5 bg-linear-to-r from-marca-acento-oscuro via-marca-acento to-marca-acento-claro" aria-hidden="true" />
    </header>
  )
}
