// frontend/src/services/datosPersonales.js
// Detección (solo para AVISAR, nunca para bloquear) de datos personales en el
// texto que se le escribe al asistente: correo, teléfono o cédula.
//
// Las mismas reglas están en el backend (EnmascaradorDatosPersonales.php), que
// es quien enmascara lo que se guarda en el historial. Si se cambian acá,
// cambiarlas allá: el aviso y el enmascarado deben coincidir.

const MIN_DIGITOS = 7;

const PATRON_CORREO = /[\p{L}\p{N}._%+-]+@[\p{L}\p{N}-]+(?:\.[\p{L}\p{N}-]+)*\.\p{L}{2,}/u;

// Dígitos que pueden venir separados por espacios, puntos o guiones
// ("300 123 4567", "1.234.567.890"). No arranca ni termina pegado a letras
// ni a guiones, para no tocar códigos como "M1-102" o "90915-YZZD4".
const PATRON_NUMERO = /(?<![\p{L}\p{N}_-])\+?\d(?:[\d .-]{5,}\d)(?![\p{L}\p{N}_])/gu;

const ES_ANIO = /^(19[5-9]\d|20\d{2}|21\d{2})$/;

function pareceDatoPersonal(candidato) {
  let grupos = candidato.split(/\D+/).filter(Boolean);

  // "1.8 2015 2019": un rango de años de un vehículo junto a otro dato
  // técnico no es una cédula. Con dos o más grupos que parecen año se
  // descartan y se evalúa solo lo que sobra.
  const anios = grupos.filter(g => ES_ANIO.test(g));
  if (anios.length >= 2) {
    grupos = grupos.filter(g => !ES_ANIO.test(g));
  }
  return grupos.join('').length >= MIN_DIGITOS;
}

/**
 * @param {string} texto
 * @returns {{ correo: boolean, numero: boolean, hay: boolean }}
 */
export function detectarDatosPersonales(texto) {
  const t = String(texto ?? '');
  const correo = PATRON_CORREO.test(t);
  const numero = Array.from(t.matchAll(PATRON_NUMERO)).some(m => pareceDatoPersonal(m[0]));
  return { correo, numero, hay: correo || numero };
}

/** Texto corto del aviso, o null si no hay nada que advertir. */
export function mensajeDatosPersonales(deteccion) {
  if (!deteccion?.hay) return null;
  const que = deteccion.correo && deteccion.numero
    ? 'un correo y un número que parece teléfono o cédula'
    : deteccion.correo
      ? 'un correo electrónico'
      : 'un número que parece teléfono o cédula';
  return `Parece que escribiste ${que}. Quítalo si es de un cliente: el asistente no lo necesita.`;
}
