import { useEffect, useState } from 'react';

const STORAGE_KEY = 'discussion_prefs_v1';

function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {
      theme: 'system',
      wallpaper: 'default',
      wallpaperDoodles: true,
      spellCheck: true,
      emojiReplace: true,
      enterToSend: true,
    };
  } catch {
    return {
      theme: 'system',
      wallpaper: 'default',
      wallpaperDoodles: true,
      spellCheck: true,
      emojiReplace: true,
      enterToSend: true,
    };
  }
}

function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === 'system') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
  } else {
    root.setAttribute('data-theme', theme);
  }
}

function applyWallpaper(wallpaper, withDoodles) {
  const root = document.documentElement;
  const WALLPAPER_COLORS = {
    default: null,
    teal: '#075e54',
    blue: '#1a2332',
    grey: '#2a2a2a',
    purple: '#3d2a4d',
    brown: '#3a2a1a',
    red: '#4a1a1a',
    'dark-teal': '#0a3d2a',
  };

  if (wallpaper === 'default') {
    root.style.setProperty('--chat-wallpaper-color', 'transparent');
    root.style.setProperty('--chat-wallpaper-opacity', '0');
    root.style.setProperty('--chat-wallpaper-pattern', 'none');
  } else {
    const color = WALLPAPER_COLORS[wallpaper];
    if (color) {
      root.style.setProperty('--chat-wallpaper-color', color);
      root.style.setProperty('--chat-wallpaper-opacity', '0.15');
      
      if (withDoodles) {
        root.style.setProperty('--chat-wallpaper-pattern', 'url("data:image/svg+xml,%3Csvg width=\'100\' height=\'100\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cdefs%3E%3Cpattern id=\'doodles\' patternUnits=\'userSpaceOnUse\' width=\'100\' height=\'100\'%3E%3Ccircle cx=\'20\' cy=\'20\' r=\'2\' fill=\'rgba(255,255,255,0.08)\'/%3E%3Ccircle cx=\'80\' cy=\'40\' r=\'1.5\' fill=\'rgba(255,255,255,0.06)\'/%3E%3Ccircle cx=\'50\' cy=\'70\' r=\'1\' fill=\'rgba(255,255,255,0.04)\'/%3E%3Ccircle cx=\'30\' cy=\'90\' r=\'1.5\' fill=\'rgba(255,255,255,0.05)\'/%3E%3Ccircle cx=\'70\' cy=\'10\' r=\'1\' fill=\'rgba(255,255,255,0.04)\'/%3E%3C/pattern%3E%3C/defs%3E%3Crect width=\'100\' height=\'100\' fill=\'url(%23doodles)\'/%3E%3C/svg%3E")');
      } else {
        root.style.setProperty('--chat-wallpaper-pattern', 'none');
      }
    }
  }
}

export function useTheme() {
  const [prefs, setPrefs] = useState(() => {
    const loaded = loadPrefs();
    // Appliquer immédiatement au chargement
    applyTheme(loaded.theme);
    applyWallpaper(loaded.wallpaper, loaded.wallpaperDoodles);
    return loaded;
  });

  useEffect(() => {
    // Écouter les changements de thème système
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      if (prefs.theme === 'system') {
        applyTheme('system');
      }
    };
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [prefs.theme]);

  // Écouter les changements dans localStorage (pour synchroniser entre composants)
  useEffect(() => {
    const handleStorageChange = () => {
      const newPrefs = loadPrefs();
      setPrefs(newPrefs);
      applyTheme(newPrefs.theme);
      applyWallpaper(newPrefs.wallpaper, newPrefs.wallpaperDoodles);
    };

    // Écouter les changements de localStorage depuis d'autres onglets
    window.addEventListener('storage', handleStorageChange);
    
    // Écouter les changements dans la même fenêtre via un événement personnalisé
    const handlePrefsChange = () => handleStorageChange();
    window.addEventListener('prefsUpdated', handlePrefsChange);

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('prefsUpdated', handlePrefsChange);
    };
  }, []);

  return prefs;
}

