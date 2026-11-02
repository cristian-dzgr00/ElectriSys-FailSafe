// frontend/src/services/asistenteDialogo.js
// Lógica pura del diálogo del asistente (sin React ni red): qué contexto se
// reenvía en el turno siguiente y cómo se separan las sugerencias confirmadas
// de las que solo comparten categoría.

export const AVISO_NO_CONFIRMADA = 'Compatibilidad no confirmada: verifica con el vehículo antes de vender.';

export const AVISO_DATOS_PERSONALES = 'No escribas datos personales de clientes: cédula, teléfono o correo.';

/**
 * Contexto a reenviar como `contexto_previo` en el próximo mensaje, o null si
 * la respuesta ya fue completa. Además de las entidades viaja la intención
 * pendiente (`_intencion_pendiente`): cuando el usuario contesta solo
 * "toyota hilux", ese texto ya no menciona ningún repuesto y el clasificador
 * podría tomarlo como otro tema; el microservicio la usa para retomar la
 * pregunta. Un backend/microservicio viejo simplemente ignora la clave.
 */
export function contextoPendienteDe(data) {
  if (!data?.esperando_datos) return null;
  const entidades = { ...(data.entidades ?? {}) };
  if (data.intencion_pendiente) entidades._intencion_pendiente = data.intencion_pendiente;
  return { entidades };
}

/**
 * Separa las sugerencias según la bandera `compatibilidad_confirmada`. Las
 * que no la traen (respuestas viejas, consultas de stock/precio) cuentan como
 * confirmadas: no se les pone un aviso que el microservicio no emitió.
 */
export function agruparSugerencias(sugerencias) {
  const lista = Array.isArray(sugerencias) ? sugerencias : [];
  return {
    confirmadas: lista.filter(s => s?.compatibilidad_confirmada !== false),
    noConfirmadas: lista.filter(s => s?.compatibilidad_confirmada === false),
  };
}

/** Texto del placeholder del campo según lo que el asistente está esperando. */
export function placeholderDe(contextoPendiente, faltanDatos) {
  if (!contextoPendiente) return 'Escribe tu consulta…';
  const faltan = Array.isArray(faltanDatos) ? faltanDatos : [];
  if (faltan.length === 1 && faltan[0] === 'modelo') return 'Responde con el modelo del vehículo…';
  if (faltan.length === 1 && faltan[0] === 'marca') return 'Responde con la marca del vehículo…';
  return 'Responde con la marca y el modelo…';
}
