import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { Saglayicilar } from './app/providers.tsx'
import { hareketUygula } from './lib/hareket.ts'

hareketUygula() // animasyon tercihi (sistem ayari ya da kullanici secimi) ilk cizimden once uygulanir

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Saglayicilar>
      <App />
    </Saglayicilar>
  </StrictMode>,
)
