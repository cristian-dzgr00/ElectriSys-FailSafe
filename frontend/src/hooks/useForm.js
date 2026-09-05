import { useState, useCallback } from 'react';

/**
 * useForm — Custom hook para formularios con validación
 * Elimina el estado duplicado en todos los forms de la app.
 *
 * @param {Object} initialValues - Valores iniciales del formulario
 * @param {Function} validate    - Función de validación: (values) => errorString | null
 */
export function useForm(initialValues, validate = null) {
  const [values,  setValues]  = useState(initialValues);
  const [error,   setError]   = useState('');
  const [saving,  setSaving]  = useState(false);
  const [touched, setTouched] = useState({});

  const set = useCallback((field, value) => {
    setValues(prev => ({ ...prev, [field]: value }));
    setTouched(prev => ({ ...prev, [field]: true }));
  }, []);

  const setMany = useCallback((updates) => {
    setValues(prev => ({ ...prev, ...updates }));
  }, []);

  const reset = useCallback((newValues = initialValues) => {
    setValues(newValues);
    setError('');
    setTouched({});
  }, [initialValues]);

  const handleSubmit = useCallback(async (submitFn) => {
    if (validate) {
      const err = validate(values);
      if (err) { setError(err); return false; }
    }
    setSaving(true);
    setError('');
    try {
      await submitFn(values);
      return true;
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Error al guardar');
      return false;
    } finally {
      setSaving(false);
    }
  }, [values, validate]);

  return { values, set, setMany, reset, error, setError, saving, touched, handleSubmit };
}
