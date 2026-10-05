import React, { useState } from 'react'
import { Dashboard } from './components/Dashboard'
import { TrainingStudio } from './components/TrainingStudio'

function App() {
  const [currentView, setCurrentView] = useState<'dashboard' | 'training'>('dashboard');

  return (
    <>
      {currentView === 'dashboard' ? (
        <Dashboard onNavigateTraining={() => setCurrentView('training')} />
      ) : (
        <TrainingStudio onBack={() => setCurrentView('dashboard')} />
      )}
    </>
  );
}

export default App

