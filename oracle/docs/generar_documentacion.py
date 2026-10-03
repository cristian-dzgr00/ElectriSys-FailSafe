"""Genera el diagrama ER (Mermaid) y el diccionario de datos del esquema ELECTRISYS.

Lee los metadatos REALES de Oracle (USER_TAB_COLUMNS, USER_CONSTRAINTS) en
vez de transcribir el DDL a mano: tipos, nulos, valores por defecto, PK,
FK, UNIQUE y CHECK salen de la base y no pueden desincronizarse. Solo las
descripciones están escritas aquí (DESCRIPCIONES).

Uso (desde la raíz del repo, con el esquema cargado):
    DB_HOST=localhost DB_PORT=1522 DB_USER=electrisys DB_PASS=... \\
        nlp-service/venv/Scripts/python oracle/docs/generar_documentacion.py

Escribe oracle/docs/diagrama_er.md y oracle/docs/diccionario_datos.md.
"""
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import oracledb

DOCS = Path(__file__).resolve().parent

# Agrupación del diagrama y del diccionario por módulo funcional.
MODULOS = {
    "Seguridad y usuarios": ["ROLES", "USUARIOS", "AUDIT_LOG", "LOGIN_ATTEMPTS"],
    "Catálogo e inventario": ["CATEGORIAS", "PROVEEDORES", "REPUESTOS", "VEHICULOS", "REPUESTO_COMPATIBILIDAD"],
    "Ventas y cotizaciones": ["CLIENTES", "VENTAS", "DETALLE_VENTAS", "COTIZACIONES", "DETALLE_COTIZACIONES"],
    "Compras a proveedor": ["PEDIDOS", "PEDIDO_DETALLE"],
    "Asistente NLP": ["NLP_INTENCIONES", "NLP_FRASES", "NLP_PREDICCIONES", "CONSULTAS_ASISTENTE", "POSIBLES_ERRORES"],
}

TABLAS = {
    "ROLES": "Roles de negocio de la aplicación (admin, vendedor, dueño). No confundir con los roles de Oracle (08_roles_privilegios.sql).",
    "USUARIOS": "Personas que inician sesión en el POS.",
    "AUDIT_LOG": "Bitácora de acciones sensibles (cambios de precio, anulaciones, inicios de sesión).",
    "LOGIN_ATTEMPTS": "Intentos de inicio de sesión por IP, para limitar ataques de fuerza bruta.",
    "CATEGORIAS": "Clasificación de los repuestos (Filtros, Frenos...).",
    "PROVEEDORES": "Empresas a las que se compran los repuestos.",
    "REPUESTOS": "Catálogo de productos con precio y existencias.",
    "VEHICULOS": "Combinaciones marca/modelo/años/motor para las que se venden repuestos. Las marcas y los modelos son columnas de esta tabla, no tablas aparte.",
    "REPUESTO_COMPATIBILIDAD": "Entidad asociativa N:M: qué repuesto le sirve a qué vehículo.",
    "CLIENTES": "Compradores identificados (la venta de mostrador puede no tener cliente).",
    "VENTAS": "Cabecera de cada venta.",
    "DETALLE_VENTAS": "Líneas de una venta: qué repuesto, cuántos y a qué precio.",
    "COTIZACIONES": "Cabecera de una cotización (presupuesto que todavía no es venta).",
    "DETALLE_COTIZACIONES": "Líneas de una cotización.",
    "PEDIDOS": "Órdenes de compra a un proveedor.",
    "PEDIDO_DETALLE": "Líneas de un pedido al proveedor.",
    "NLP_INTENCIONES": "Catálogo de las 7 intenciones que reconoce el asistente.",
    "NLP_FRASES": "Frases de entrenamiento y de prueba (holdout) del clasificador de intención.",
    "NLP_PREDICCIONES": "Resultado de evaluar el clasificador frase por frase.",
    "CONSULTAS_ASISTENTE": "Log de cada consulta hecha al asistente, con su respuesta y la valoración del usuario.",
    "POSIBLES_ERRORES": "Formas mal escritas de marcas, modelos y categorías que el NER reconoce (\"jilus\" -> \"Hilux\").",
}

COMUNES = {
    "ID": "Identificador sustituto (IDENTITY).",
    "CREADO_EN": "Fecha y hora de creación.",
    "CREATED_AT": "Fecha y hora del registro.",
    "UPDATED_AT": "Última modificación (la mantiene un trigger: Oracle no tiene ON UPDATE).",
    "DELETED_AT": "Borrado lógico: fecha en que se dio de baja; NULL si está vigente.",
    "ACTIVO": "1 activo, 0 inactivo.",
    "NOTAS": "Observaciones libres.",
    "EMAIL": "Correo electrónico.",
    "TELEFONO": "Teléfono de contacto.",
    "DIRECCION": "Dirección postal.",
}

DESCRIPCIONES = {
    "ROLES": {"NOMBRE": "Nombre del rol: admin, vendedor o dueno."},
    "USUARIOS": {"NOMBRE": "Nombre para mostrar.", "PASSWORD": "Hash bcrypt de la contraseña (nunca el texto plano).",
                 "ROL_ID": "Rol de negocio del usuario."},
    "AUDIT_LOG": {"USUARIO_ID": "Quién hizo la acción. Sin FK a propósito: el log sobrevive a cambios en USUARIOS.",
                  "ACCION": "Código de la acción (crear_venta, cambio_precio...).", "DETALLE": "Descripción legible del cambio.",
                  "IP": "Dirección IP del cliente (IPv4 o IPv6)."},
    "LOGIN_ATTEMPTS": {"IP": "IP que intentó iniciar sesión."},
    "CATEGORIAS": {"NOMBRE": "Nombre de la categoría."},
    "PROVEEDORES": {"NOMBRE": "Razón social.", "CONTACTO": "Persona de contacto."},
    "REPUESTOS": {"CODIGO": "Código de referencia del fabricante o interno.", "NOMBRE": "Nombre comercial.",
                  "DESCRIPCION": "Descripción ampliada.", "CATEGORIA_ID": "Categoría del repuesto.",
                  "PROVEEDOR_ID": "Proveedor habitual.", "PRECIO_COMPRA": "Costo unitario.",
                  "PRECIO_VENTA": "Precio unitario de venta vigente.", "STOCK": "Unidades disponibles (lo mueven triggers de ventas y pedidos).",
                  "STOCK_MINIMO": "Umbral de alerta de reabastecimiento."},
    "VEHICULOS": {"MARCA": "Marca del vehículo (Toyota).", "MODELO": "Modelo (Hilux).", "ANIO_DESDE": "Primer año del rango.",
                  "ANIO_HASTA": "Último año del rango.", "MOTOR": "Cilindrada o código de motor (2.7, 1600cc).",
                  "COMBUSTIBLE": "Tipo de combustible."},
    "REPUESTO_COMPATIBILIDAD": {"REPUESTO_ID": "Repuesto compatible.", "VEHICULO_ID": "Vehículo con el que es compatible."},
    "CLIENTES": {"NOMBRE": "Nombre o razón social.", "IDENTIFICACION": "Número de documento.", "TIPO_DOC": "Tipo de documento."},
    "VENTAS": {"NUMERO": "Número de factura visible para el cliente.", "CLIENTE_ID": "Cliente (NULL en venta de mostrador).",
               "USUARIO_ID": "Vendedor que registró la venta.", "SUBTOTAL": "Suma de las líneas antes de descuento e impuesto.",
               "DESCUENTO": "Descuento global.", "IMPUESTO": "Impuesto calculado.", "TOTAL": "Total cobrado.",
               "METODO_PAGO": "Forma de pago.", "ESTADO": "Estado de la venta (anulada devuelve el stock).",
               "VERSION": "Control de concurrencia optimista: se incrementa en cada actualización."},
    "DETALLE_VENTAS": {"VENTA_ID": "Venta a la que pertenece la línea.", "REPUESTO_ID": "Repuesto vendido.",
                       "CANTIDAD": "Unidades vendidas.", "PRECIO_UNIT": "Precio unitario al momento de la venta (histórico).",
                       "DESCUENTO": "Descuento de la línea.", "SUBTOTAL": "cantidad x precio_unit - descuento."},
    "COTIZACIONES": {"NUMERO": "Número de cotización.", "CLIENTE_ID": "Cliente que la pidió.", "USUARIO_ID": "Vendedor que la hizo.",
                     "SUBTOTAL": "Suma de las líneas.", "DESCUENTO": "Descuento global.", "IMPUESTO": "Impuesto.",
                     "TOTAL": "Total cotizado.", "ESTADO": "activa, vencida (cambió un precio) o realizada (se volvió venta).",
                     "VENCE_EN": "Fecha estimada informada al cliente (no cambia el estado)."},
    "DETALLE_COTIZACIONES": {"COTIZACION_ID": "Cotización de la línea.", "REPUESTO_ID": "Repuesto cotizado.",
                             "CANTIDAD": "Unidades.", "PRECIO_UNIT": "Precio cotizado.", "DESCUENTO": "Descuento de la línea.",
                             "SUBTOTAL": "Total de la línea."},
    "PEDIDOS": {"NUMERO": "Número del pedido (lo asigna un trigger con una secuencia).", "PROVEEDOR_ID": "Proveedor al que se compra.",
                "USUARIO_ID": "Quién hizo el pedido.", "ESTADO": "Ciclo del pedido; al pasar a recibido suma stock.",
                "SUBTOTAL": "Suma de las líneas.", "TOTAL": "Total del pedido.", "FECHA_ESPERADA": "Fecha estimada de llegada.",
                "RECIBIDO_EN": "Cuándo se recibió (solo al pasar a recibido)."},
    "PEDIDO_DETALLE": {"PEDIDO_ID": "Pedido de la línea.", "REPUESTO_ID": "Repuesto pedido.", "CANTIDAD": "Unidades pedidas.",
                       "PRECIO_UNIT": "Precio de COMPRA acordado (no el de venta).", "SUBTOTAL": "Total de la línea."},
    "NLP_INTENCIONES": {"NOMBRE": "Identificador de la intención (buscar_repuesto...).", "DESCRIPCION": "Qué pide el usuario.",
                        "RESPUESTA": "Cómo responde el asistente (consulta el catálogo o respuesta fija)."},
    "NLP_FRASES": {"TEXTO": "Frase de ejemplo tal como la escribiría un vendedor.", "INTENCION_ID": "Intención correcta (etiqueta).",
                   "CONJUNTO": "entrenamiento u holdout (prueba que el modelo nunca ve).", "N_CARACTERES": "Longitud en caracteres.",
                   "N_PALABRAS": "Longitud en palabras.", "FUENTE": "Archivo de origen de la frase."},
    "NLP_PREDICCIONES": {"FRASE_ID": "Frase evaluada.", "METODO": "Cómo se evaluó: validación cruzada u holdout.",
                         "INTENCION_PRED": "Intención que predijo el modelo.", "CONFIANZA": "Probabilidad de la predicción (0 a 1).",
                         "CORRECTA": "1 si coincide con la etiqueta de la frase.", "MODELO": "Versión del modelo evaluado."},
    "CONSULTAS_ASISTENTE": {"USUARIO_ID": "Quién consultó.", "TEXTO_CONSULTA": "Texto escrito por el usuario.",
                            "INTENCION_DETECTADA": "Intención que detectó el asistente.", "ENTIDADES_JSON": "Marca, modelo, año... extraídos (JSON nativo).",
                            "RESPUESTA_JSON": "Respuesta completa del asistente (JSON nativo).", "UTIL": "Valoración: 1 útil, 0 no útil, NULL sin votar."},
    "POSIBLES_ERRORES": {"TIPO": "Entidad a la que pertenece: marca, modelo o categoria.",
                         "ERROR": "Forma mal escrita, ya normalizada (minúsculas, sin tildes ni puntuación).",
                         "CORRECTO": "Nombre oficial tal como está en el catálogo.",
                         "NIVEL": "1 una letra, 2 fonético/apodo, 3 dos errores, 4 reservado.",
                         "ORIGEN": "auto (generador) o manual.", "NOTA": "Tipo de error (letra repetida, fonético...).",
                         "ACTUALIZADO_EN": "Última actualización por MERGE."},
}

ABREVIATURA_TIPO = {"VARCHAR2": "VARCHAR2", "NUMBER": "NUMBER", "TIMESTAMP(6)": "TIMESTAMP", "DATE": "DATE", "JSON": "JSON"}


def conectar():
    faltan = [v for v in ("DB_HOST", "DB_USER", "DB_PASS") if not os.getenv(v)]
    if faltan:
        sys.exit(f"Faltan variables de entorno: {', '.join(faltan)}")
    dsn = f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '1521')}/{os.getenv('DB_SERVICE_NAME', 'FREEPDB1')}"
    return oracledb.connect(user=os.getenv("DB_USER"), password=os.getenv("DB_PASS"), dsn=dsn)


def leer_metadatos(cur):
    cur.execute("""
        SELECT table_name, column_name, data_type, data_length, data_precision, data_scale,
               nullable, data_default, identity_column, column_id
          FROM user_tab_columns
         WHERE table_name IN (SELECT table_name FROM user_tables)
         ORDER BY table_name, column_id""")
    columnas = defaultdict(list)
    for t, c, tipo, largo, prec, esc, nulo, defecto, ident, _ in cur:
        if tipo == "VARCHAR2":
            tipo_txt = f"VARCHAR2({largo})"
        elif tipo == "NUMBER" and prec is not None:
            tipo_txt = f"NUMBER({prec},{esc})" if esc else f"NUMBER({prec})"
        else:
            tipo_txt = ABREVIATURA_TIPO.get(tipo, tipo)
        defecto = (defecto or "").strip()
        columnas[t].append({"columna": c, "tipo": tipo_txt, "nulo": nulo == "Y",
                            "defecto": "" if ident == "YES" or defecto.upper() == "NULL" else defecto,
                            "identity": ident == "YES"})
    cur.execute("""
        SELECT c.table_name, c.constraint_name, c.constraint_type,
               LISTAGG(cc.column_name, ', ') WITHIN GROUP (ORDER BY cc.position),
               c.search_condition_vc, r.table_name, c.delete_rule, c.validated
          FROM user_constraints c
          JOIN user_cons_columns cc ON cc.constraint_name = c.constraint_name
          LEFT JOIN user_constraints r ON r.constraint_name = c.r_constraint_name
         WHERE c.table_name IN (SELECT table_name FROM user_tables)
           AND c.constraint_type IN ('P', 'R', 'U', 'C')
         GROUP BY c.table_name, c.constraint_name, c.constraint_type, c.search_condition_vc,
                  r.table_name, c.delete_rule, c.validated""")
    restricciones = defaultdict(list)
    for t, nombre, tipo, cols, condicion, ref, borrar, validada in cur:
        # Los NOT NULL también son CHECK en el diccionario de Oracle: ya se
        # muestran en la columna "Nulo", no se repiten.
        if tipo == "C" and condicion and re.fullmatch(r'"?\w+"? IS NOT NULL', condicion.strip()):
            continue
        restricciones[t].append({"nombre": nombre, "tipo": tipo, "columnas": cols, "condicion": condicion,
                                 "ref": ref, "borrar": borrar, "validada": validada})
    return columnas, restricciones


def restricciones_de_columna(columna, restricciones):
    marcas = []
    for r in restricciones:
        cols = [c.strip() for c in r["columnas"].split(",")]
        if columna not in cols:
            continue
        compuesta = len(cols) > 1
        if r["tipo"] == "P":
            marcas.append("PK")
        elif r["tipo"] == "R":
            extra = " ON DELETE CASCADE" if r["borrar"] == "CASCADE" else ""
            extra += " (NOVALIDATE)" if r["validada"] == "NOT VALIDATED" else ""
            marcas.append(f"FK → {r['ref']}{extra}")
        elif r["tipo"] == "U":
            marcas.append(f"UNIQUE ({r['columnas']})" if compuesta else "UNIQUE")
        elif r["tipo"] == "C":
            marcas.append(f"CHECK ({r['condicion'].strip()})")
    return marcas


def diccionario(columnas, restricciones) -> str:
    lineas = [
        "# Diccionario de datos — esquema ELECTRISYS",
        "",
        "Generado por `oracle/docs/generar_documentacion.py` desde los metadatos de Oracle 23ai",
        "(`USER_TAB_COLUMNS`, `USER_CONSTRAINTS`). Los tipos y las restricciones son los de la",
        "base real; no editar a mano, volver a generar.",
        "",
        f"**{len(columnas)} tablas**, "
        f"{sum(len(v) for v in columnas.values())} columnas, "
        f"{sum(1 for v in restricciones.values() for r in v if r['tipo'] == 'R')} claves foráneas, "
        f"{sum(1 for v in restricciones.values() for r in v if r['tipo'] == 'U')} restricciones UNIQUE y "
        f"{sum(1 for v in restricciones.values() for r in v if r['tipo'] == 'C')} CHECK.",
        "",
        "Convenciones: todas las PK son `NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY`; los booleanos",
        "son `NUMBER(1)` (0/1) porque el backend PHP compara `= 1`; los ENUM de MySQL son `VARCHAR2` + `CHECK`.",
        "",
    ]
    for modulo, tablas in MODULOS.items():
        lineas += [f"## {modulo}", ""]
        for t in tablas:
            if t not in columnas:
                continue
            lineas += [f"### {t.lower()}", "", TABLAS.get(t, ""), "",
                       "| Columna | Tipo | Nulo | Por defecto | Restricciones | Descripción |",
                       "|---|---|---|---|---|---|"]
            for c in columnas[t]:
                desc = DESCRIPCIONES.get(t, {}).get(c["columna"]) or COMUNES.get(c["columna"], "")
                marcas = restricciones_de_columna(c["columna"], restricciones[t])
                defecto = "IDENTITY" if c["identity"] else c["defecto"].replace("|", "\\|")
                lineas.append("| {} | {} | {} | {} | {} | {} |".format(
                    c["columna"].lower(), c["tipo"], "sí" if c["nulo"] else "no", defecto,
                    "<br>".join(m.replace("|", "\\|") for m in marcas), desc))
            lineas.append("")
    return "\n".join(lineas)


def diagrama(columnas, restricciones) -> str:
    lineas = [
        "# Diagrama entidad-relación — esquema ELECTRISYS",
        "",
        "Generado por `oracle/docs/generar_documentacion.py` desde las claves foráneas reales de",
        "Oracle. GitHub y VS Code (extensión Markdown Preview Mermaid) lo muestran como diagrama.",
        "",
        "Lectura de las relaciones: `||` exactamente uno, `|o` cero o uno (FK que admite NULL),",
        "`o{` cero o muchos. Las entidades asociativas (DETALLE_*, REPUESTO_COMPATIBILIDAD) resuelven",
        "las relaciones N:M.",
        "",
        "```mermaid",
        "erDiagram",
    ]
    nulos = {(t, c["columna"]): c["nulo"] for t, cols in columnas.items() for c in cols}
    for t, rs in sorted(restricciones.items()):
        for r in sorted(rs, key=lambda x: x["nombre"]):
            if r["tipo"] != "R":
                continue
            padre_lado = "|o" if nulos.get((t, r["columnas"])) else "||"
            etiqueta = r["columnas"].lower() + (" (cascade)" if r["borrar"] == "CASCADE" else "")
            lineas.append(f'    {r["ref"]} {padre_lado}--o{{ {t} : "{etiqueta}"')
    for t in sorted(columnas):
        lineas.append(f"    {t} {{")
        claves = defaultdict(list)
        for r in restricciones[t]:
            for col in [c.strip() for c in r["columnas"].split(",")]:
                if r["tipo"] == "P":
                    claves[col].append("PK")
                elif r["tipo"] == "R":
                    claves[col].append("FK")
                elif r["tipo"] == "U":
                    claves[col].append("UK")
        for c in columnas[t]:
            tipo = re.sub(r"[^A-Za-z0-9_]", "_", c["tipo"]).strip("_")
            marca = ",".join(dict.fromkeys(claves.get(c["columna"], [])))
            lineas.append(f"        {tipo} {c['columna'].lower()}{(' ' + marca) if marca else ''}")
        lineas.append("    }")
    lineas += [
        "```",
        "",
        "## Tablas sin relaciones declaradas (a propósito)",
        "",
        "- **posibles_errores**: `correcto` apunta a `vehiculos.marca`, `vehiculos.modelo` o",
        "  `categorias.nombre` según el valor de `tipo`; una FK no puede elegir destino por el valor",
        "  de otra columna. Ver `normalizacion.md`, decisión D4.",
        "- **audit_log.usuario_id**: sin FK para que el log sobreviva a cualquier cambio en usuarios.",
        "- **login_attempts**: registra IPs, no usuarios (el intento puede ser de un usuario inexistente).",
        "",
    ]
    return "\n".join(lineas)


def main():
    with conectar() as conexion, conexion.cursor() as cur:
        columnas, restricciones = leer_metadatos(cur)
    (DOCS / "diccionario_datos.md").write_text(diccionario(columnas, restricciones), encoding="utf-8")
    (DOCS / "diagrama_er.md").write_text(diagrama(columnas, restricciones), encoding="utf-8")
    print(f"{len(columnas)} tablas documentadas en {DOCS}")


if __name__ == "__main__":
    main()
