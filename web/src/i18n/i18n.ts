/**
 * ALIS i18n initialisation
 *
 * Supported locales: en (default), hi, te, kn, ta, mr
 * Language preference is stored in the user profile (PATCH /users/{id} language_preference).
 * Student/parent-facing strings only — staff UI remains in English.
 */
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './en.json'
import hi from './hi.json'
import te from './te.json'
import kn from './kn.json'
import ta from './ta.json'
import mr from './mr.json'

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      hi: { translation: hi },
      te: { translation: te },
      kn: { translation: kn },
      ta: { translation: ta },
      mr: { translation: mr },
    },
    lng: localStorage.getItem('alis_lang') ?? 'en',
    fallbackLng: 'en',
    interpolation: { escapeValue: false },
  })

export default i18n
