// Navegación con React Router (ADR 0005). El router (BrowserRouter) se pone en main.jsx
// para que las pruebas puedan usar MemoryRouter con la ruta que necesiten.
import { Link, Route, Routes, useLocation } from 'react-router'
import Cabecera from './componentes/Cabecera.jsx'
import EstadoServidor from './componentes/EstadoServidor.jsx'
import Onda from './componentes/Onda.jsx'
import PaginaAdmin from './paginas/PaginaAdmin.jsx'
import PaginaListas from './paginas/PaginaListas.jsx'
import PaginaNecesidad from './paginas/PaginaNecesidad.jsx'
import PaginaNuevaNecesidad from './paginas/PaginaNuevaNecesidad.jsx'
import PaginaPanel from './paginas/PaginaPanel.jsx'
import PaginaRetrasosProveedor from './paginas/PaginaRetrasosProveedor.jsx'

// «Nueva necesidad» es la acción principal: va la última y como botón.
const ENLACES = [
  { href: '/', texto: 'Panel' },
  { href: '/listas', texto: 'Proveedores y peticionarios' },
  { href: '/nueva', texto: 'Nueva necesidad', destacado: true },
]

export default function App() {
  const { pathname } = useLocation()
  return (
    <div className="flex min-h-screen flex-col bg-white text-marca-texto">
      <EstadoServidor />
      <Cabecera enlaces={ENLACES} />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 md:py-10">
        <Routes>
          <Route path="/" element={<PaginaPanel />} />
          {/* Claves distintas: al pasar de «Corregir» a «Nueva necesidad» el formulario empieza vacío. */}
          <Route path="/nueva" element={<PaginaNuevaNecesidad key="nueva" />} />
          <Route path="/necesidades/:id" element={<PaginaNecesidad />} />
          <Route path="/necesidades/:id/editar" element={<PaginaNuevaNecesidad key="editar" />} />
          <Route path="/listas" element={<PaginaListas />} />
          <Route path="/proveedores/:id/retrasos" element={<PaginaRetrasosProveedor />} />
          {/* Modo admin (ADR 0015): se llega con el enlace discreto «admin» del pie. */}
          <Route path="/admin" element={<PaginaAdmin />} />
          <Route path="*" element={<p className="text-slate-600">Esta pantalla todavía no existe.</p>} />
        </Routes>
      </main>
      {/* La onda solo en la página de inicio (guía de estilo), unida al pie oscuro. */}
      {pathname === '/' && <Onda />}
      <footer className={pathname === '/' ? 'bg-marca-oscuro text-white/70' : 'border-t border-slate-200 text-slate-500'}>
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-4 text-xs sm:px-6">
          <p>ReMate, desarrollado por Laro Señas</p>
          {/* Modo admin (ADR 0015): enlace discreto, del color del pie. Protege la contraseña, no el enlace. */}
          <Link to="/admin" className="hover:underline">
            admin
          </Link>
        </div>
      </footer>
    </div>
  )
}
