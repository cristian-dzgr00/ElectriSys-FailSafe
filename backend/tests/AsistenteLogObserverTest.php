<?php
use PHPUnit\Framework\TestCase;
use App\models\OciConnection;
use App\models\OciStatement;
use App\patterns\observer\AsistenteLogObserver;
use App\patterns\observer\GestorAsistente;
use App\services\ConsultasAsistenteListado;

/**
 * Statement falso: registra el SQL y los parámetros de cada execute() y, si
 * se le pide, simula un error de Oracle en la N-ésima ejecución del SQL que
 * contenga cierto texto.
 */
class StatementFalso extends OciStatement
{
    public array $ejecuciones = [];
    private mixed $salidaId = null;
    private array $filas = [];

    public function __construct(
        public string $sql,
        private ConexionFalsa $conexion
    ) {}

    public function bindOut(string $nombre, &$variable, int $maxLength = 40): void
    {
        $this->salidaId = &$variable;
    }

    public function execute(array $params = []): bool
    {
        $this->conexion->registrar($this->sql, $params);
        if ($this->conexion->fallarEn !== null && str_contains($this->sql, $this->conexion->fallarEn)) {
            throw new \RuntimeException('ORA-00904: "RESPUESTA_JSON": invalid identifier');
        }
        if ($this->salidaId !== null) {
            $this->salidaId = $this->conexion->idDeLaConsulta;
        }
        $this->filas = $this->conexion->resultados[$this->conexion->tablaDe($this->sql)] ?? [];
        return true;
    }

    public function fetchAll(): array
    {
        return $this->filas;
    }
}

/** Conexión falsa: guarda todo lo que se ejecuta, en orden, y las llamadas de transacción. */
class ConexionFalsa extends OciConnection
{
    /** @var array<int,array{sql:string,params:array}> */
    public array $ejecutadas = [];
    /** @var string[] */
    public array $eventos = [];
    public int $idDeLaConsulta = 77;
    public ?string $fallarEn = null;
    public bool $rollbackLanza = false;
    /** @var array<string,array> filas devueltas por tabla, para las lecturas */
    public array $resultados = [];

    public function __construct() {}

    public function prepare(string $sql): OciStatement
    {
        $this->eventos[] = 'prepare:' . $this->tablaDe($sql);
        return new StatementFalso($sql, $this);
    }

    public function beginTransaction(): bool { $this->eventos[] = 'begin'; return true; }
    public function commit(): bool { $this->eventos[] = 'commit'; return true; }
    public function rollBack(): bool
    {
        $this->eventos[] = 'rollback';
        if ($this->rollbackLanza) {
            throw new \RuntimeException('rollback falló');
        }
        return true;
    }

    public function registrar(string $sql, array $params): void
    {
        $this->ejecutadas[] = ['sql' => $sql, 'params' => $params];
        $this->eventos[] = 'execute:' . $this->tablaDe($sql);
    }

    public function tablaDe(string $sql): string
    {
        if (preg_match('/(?:INSERT\s+INTO|FROM)\s+(\w+)/i', $sql, $m)) {
            return strtolower($m[1]);
        }
        return '?';
    }

    /** Ejecuciones de INSERT sobre una tabla. */
    public function insertsEn(string $tabla): array
    {
        return array_values(array_filter(
            $this->ejecutadas,
            fn($e) => preg_match('/INSERT\s+INTO\s+' . $tabla . '\b/i', $e['sql']) === 1
        ));
    }
}

/**
 * AsistenteLogObserver contra el esquema normalizado (3FN fase 2): la consulta
 * va a consultas_asistente (con intencion_id y confianza) y sus entidades y
 * recomendaciones a tablas hijas, todo en una sola transacción. No toca la BD:
 * usa una conexión falsa que registra el SQL y los parámetros.
 */
class AsistenteLogObserverTest extends TestCase
{
    private ConexionFalsa $db;
    private AsistenteLogObserver $observer;
    private string $logOriginal;

    protected function setUp(): void
    {
        $this->db = new ConexionFalsa();
        $this->observer = new AsistenteLogObserver($this->db);
        // error_log() de los casos de fallo no debe ensuciar la salida de las pruebas.
        $this->logOriginal = (string) ini_get('error_log');
        ini_set('error_log', sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'electrisys_test_asistente.log');
    }

    protected function tearDown(): void
    {
        ini_set('error_log', $this->logOriginal);
    }

    private function contexto(array $respuesta, string $texto = 'filtro de aceite para Toyota Hilux 2024'): array
    {
        return ['usuario_id' => 5, 'texto_consulta' => $texto, 'respuesta' => $respuesta, 'ip' => '10.0.0.1'];
    }

    public function testNingunaSentenciaMencionaLasColumnasJsonEliminadas(): void
    {
        $this->observer->actualizar('consulta_asistente', $this->contexto([
            'intencion' => 'buscar_repuesto', 'confianza' => 0.91,
            'entidades' => ['marca' => 'Toyota'], 'sugerencias' => [['id' => 10, 'similitud' => 0.5]],
        ]));

        foreach ($this->db->ejecutadas as $e) {
            $this->assertDoesNotMatchRegularExpression('/intencion_detectada|entidades_json|respuesta_json/i', $e['sql']);
        }
    }

    public function testInsertaLaConsultaConIntencionIdYConfianza(): void
    {
        $this->observer->actualizar('consulta_asistente', $this->contexto([
            'intencion' => 'buscar_repuesto', 'confianza' => 0.9123456,
        ]));

        $inserts = $this->db->insertsEn('consultas_asistente');
        $this->assertCount(1, $inserts);
        $sql = $inserts[0]['sql'];
        $this->assertStringContainsString('usuario_id, texto_consulta, intencion_id, confianza', $sql);
        $this->assertStringContainsString('SELECT i.id FROM nlp_intenciones i WHERE i.nombre = :intencion', $sql);
        $this->assertStringContainsString('RETURNING id INTO :out_id', $sql);
        $this->assertSame(5, $inserts[0]['params'][':usuario_id']);
        $this->assertSame('buscar_repuesto', $inserts[0]['params'][':intencion']);
        $this->assertSame(0.9123, $inserts[0]['params'][':confianza']);
        $this->assertSame(77, $this->observer->ultimoIdInsertado());
    }

    public function testIntencionDesconocidaOAusenteSeEnviaNulaParaQueIntencionIdQuedeNulo(): void
    {
        // El nombre desconocido se envía tal cual: el sub-SELECT no encuentra fila y da NULL.
        $this->observer->actualizar('consulta_asistente', $this->contexto(['intencion' => 'intencion_que_no_existe']));
        $this->assertSame('intencion_que_no_existe', $this->db->insertsEn('consultas_asistente')[0]['params'][':intencion']);
        $this->assertStringContainsString('(SELECT i.id FROM nlp_intenciones', $this->db->insertsEn('consultas_asistente')[0]['sql']);

        $this->db->ejecutadas = [];
        $this->observer->actualizar('consulta_asistente', $this->contexto([]));
        $params = $this->db->insertsEn('consultas_asistente')[0]['params'];
        $this->assertNull($params[':intencion']);
        $this->assertNull($params[':confianza']);
        $this->assertSame(77, $this->observer->ultimoIdInsertado());
    }

    public function testConfianzaIlegibleOFueraDeRangoQuedaNula(): void
    {
        foreach ([1.5, -0.1, 'abc', null, [0.5]] as $valor) {
            $this->db->ejecutadas = [];
            $this->observer->actualizar('consulta_asistente', $this->contexto(['intencion' => 'saludo_despedida', 'confianza' => $valor]));
            $this->assertNull($this->db->insertsEn('consultas_asistente')[0]['params'][':confianza']);
        }
    }

    public function testUnaFilaPorEntidadConLosTiposDeLaMigracion(): void
    {
        $this->observer->actualizar('consulta_asistente', $this->contexto([
            'intencion' => 'buscar_repuesto', 'confianza' => 0.8,
            'entidades' => [
                'marca' => 'Toyota', 'modelo' => 'Hilux', 'anio' => 2024, 'categoria' => 'frenos',
                'codigo' => 'BR-100',
                'motor' => '2.7', 'combustible' => 'gasolina', // sin tipo permitido: no se guardan
                'vacio' => '', 'nulo' => null,
            ],
        ]));

        $filas = $this->db->insertsEn('consulta_entidades');
        $this->assertCount(5, $filas);
        $this->assertSame(
            ['marca' => 'Toyota', 'modelo' => 'Hilux', 'anio' => '2024', 'categoria' => 'frenos', 'repuesto' => 'BR-100'],
            array_column(array_map(fn($f) => [$f['params'][':tipo'], $f['params'][':valor']], $filas), 1, 0)
        );
        foreach ($filas as $f) {
            $this->assertSame(77, $f['params'][':consulta_id']);
        }
    }

    public function testEntidadesNulasVaciasONoEscalaresNoGeneranFilas(): void
    {
        $this->observer->actualizar('consulta_asistente', $this->contexto([
            'intencion' => 'saludo_despedida', 'entidades' => ['marca' => null, 'modelo' => '  ', 'anio' => ['x'], 'categoria' => true],
        ]));
        $this->assertCount(0, $this->db->insertsEn('consulta_entidades'));

        $this->observer->actualizar('consulta_asistente', $this->contexto(['intencion' => 'saludo_despedida', 'entidades' => null]));
        $this->assertCount(0, $this->db->insertsEn('consulta_entidades'));
    }

    public function testUnaFilaPorRecomendacionConPosicionPuntajeYSustituto(): void
    {
        $this->observer->actualizar('consulta_asistente', $this->contexto([
            'intencion' => 'recomendar_sustituto', 'confianza' => 0.7,
            'sugerencias' => [
                ['id' => 10, 'similitud' => 0.8734],
                ['id' => 11, 'similitud' => 0.5],
                ['id' => 10, 'similitud' => 0.4],      // repetido: PK consulta+repuesto, cuenta una vez
                ['id' => 12],                           // sin similitud: puntaje NULL
                ['nombre' => 'sin id'],                 // sin id: se omite
            ],
        ]));

        $filas = $this->db->insertsEn('consulta_recomendaciones');
        $this->assertCount(3, $filas);
        $this->assertStringContainsString('FROM repuestos r WHERE r.id = :repuesto_id', $filas[0]['sql']);

        $this->assertSame(10, $filas[0]['params'][':repuesto_id']);
        $this->assertSame(1, $filas[0]['params'][':posicion']);
        $this->assertSame(87.34, $filas[0]['params'][':puntaje']);
        $this->assertSame(1, $filas[0]['params'][':es_sustituto']);
        $this->assertSame(77, $filas[0]['params'][':consulta_id']);

        $this->assertSame(11, $filas[1]['params'][':repuesto_id']);
        $this->assertSame(2, $filas[1]['params'][':posicion']);
        $this->assertSame(50.0, $filas[1]['params'][':puntaje']);

        // La posición es la del arreglo original (la 3ª se descartó por repetida, la 4ª sigue siendo la 4ª).
        $this->assertSame(12, $filas[2]['params'][':repuesto_id']);
        $this->assertSame(4, $filas[2]['params'][':posicion']);
        $this->assertNull($filas[2]['params'][':puntaje']);
    }

    public function testEsSustitutoSoloCuandoLaIntencionEsRecomendarSustituto(): void
    {
        $this->observer->actualizar('consulta_asistente', $this->contexto([
            'intencion' => 'buscar_repuesto', 'sugerencias' => [['id' => 10, 'similitud' => 0.5]],
        ]));
        $this->assertSame(0, $this->db->insertsEn('consulta_recomendaciones')[0]['params'][':es_sustituto']);
    }

    public function testToDoSucedeEnUnaTransaccionYSeConfirmaAlFinal(): void
    {
        $this->observer->actualizar('consulta_asistente', $this->contexto([
            'intencion' => 'buscar_repuesto', 'entidades' => ['marca' => 'Toyota'],
            'sugerencias' => [['id' => 10, 'similitud' => 0.5]],
        ]));

        $this->assertSame('begin', $this->db->eventos[0]);
        $this->assertSame('commit', end($this->db->eventos));
        $this->assertNotContains('rollback', $this->db->eventos);
        $this->assertCount(1, array_keys($this->db->eventos, 'commit', true));
        // begin antes de preparar la primera sentencia (para que use OCI_NO_AUTO_COMMIT).
        $this->assertLessThan(
            array_search('prepare:consultas_asistente', $this->db->eventos, true),
            array_search('begin', $this->db->eventos, true)
        );
    }

    public function testSiFallaUnHijoSeHaceRollbackNoSeConfirmaYNoSePropagaElError(): void
    {
        $this->db->fallarEn = 'consulta_recomendaciones';

        $this->observer->actualizar('consulta_asistente', $this->contexto([
            'intencion' => 'buscar_repuesto', 'entidades' => ['marca' => 'Toyota'],
            'sugerencias' => [['id' => 10, 'similitud' => 0.5]],
        ]));

        $this->assertContains('rollback', $this->db->eventos);
        $this->assertNotContains('commit', $this->db->eventos);
        $this->assertNull($this->observer->ultimoIdInsertado(), 'sin commit no hay id vigente');
    }

    public function testSiFallaLaConsultaPrincipalNoSeIntentanHijosYSeHaceRollback(): void
    {
        $this->db->fallarEn = 'consultas_asistente';

        $this->observer->actualizar('consulta_asistente', $this->contexto([
            'intencion' => 'buscar_repuesto', 'entidades' => ['marca' => 'Toyota'],
        ]));

        $this->assertCount(0, $this->db->insertsEn('consulta_entidades'));
        $this->assertSame(['begin', 'prepare:consultas_asistente', 'execute:consultas_asistente', 'rollback'], $this->db->eventos);
        $this->assertNull($this->observer->ultimoIdInsertado());
    }

    public function testUnRollbackQueFallaTampocoRompeLaRespuestaAlUsuario(): void
    {
        $this->db->fallarEn = 'consultas_asistente';
        $this->db->rollbackLanza = true;

        $this->observer->actualizar('consulta_asistente', $this->contexto(['intencion' => 'buscar_repuesto']));

        $this->assertNull($this->observer->ultimoIdInsertado());
    }

    public function testElIdDeUnFalloNoSeConfundeConElDeLaConsultaAnterior(): void
    {
        $this->observer->actualizar('consulta_asistente', $this->contexto(['intencion' => 'buscar_repuesto']));
        $this->assertSame(77, $this->observer->ultimoIdInsertado());

        $this->db->fallarEn = 'consultas_asistente';
        $this->observer->actualizar('consulta_asistente', $this->contexto(['intencion' => 'buscar_repuesto']));
        $this->assertNull($this->observer->ultimoIdInsertado());
    }

    public function testElTextoYLasEntidadesRegistradosSiguenEnmascarados(): void
    {
        // Mismo recorrido que en produccion: GestorAsistente enmascara y luego notifica al observer real.
        $gestor = new class extends GestorAsistente {
            protected function llamarMicroservicio(string $texto, ?array $contextoPrevio = null): array
            {
                return [
                    'intencion' => 'consultar_stock', 'confianza' => 0.95,
                    'entidades' => ['codigo' => '7701234567890'],
                    'sugerencias' => [], 'respuesta_texto' => 'ok',
                ];
            }
        };
        $gestor->agregarObserver($this->observer);

        $devuelta = $gestor->consultar('stock del 7701234567890, avisar a cliente@correo.com o al 3001234567', 5, '10.0.0.1');

        $this->assertSame(
            'stock del ***, avisar a *** o al ***',
            $this->db->insertsEn('consultas_asistente')[0]['params'][':texto_consulta']
        );
        $entidad = $this->db->insertsEn('consulta_entidades');
        $this->assertCount(1, $entidad);
        $this->assertSame('repuesto', $entidad[0]['params'][':tipo']);
        $this->assertSame('***', $entidad[0]['params'][':valor']);
        // El vendedor sigue recibiendo la respuesta sin enmascarar y con el id registrado.
        $this->assertSame('7701234567890', $devuelta['entidades']['codigo']);
        $this->assertSame(77, $devuelta['consulta_id']);
    }

    public function testElListadoReconstruyeLaFormaAnteriorDesdeLasTablasNormalizadas(): void
    {
        $this->db->resultados = [
            'consulta_entidades' => [
                ['consulta_id' => 3, 'tipo' => 'marca', 'valor' => 'Toyota'],
                ['consulta_id' => 3, 'tipo' => 'repuesto', 'valor' => 'BR-100'],
            ],
            'consulta_recomendaciones' => [
                ['consulta_id' => 3, 'repuesto_id' => 10, 'posicion' => 1, 'es_sustituto' => 1, 'puntaje' => 87.5],
                ['consulta_id' => 3, 'repuesto_id' => 11, 'posicion' => 2, 'es_sustituto' => 1, 'puntaje' => null],
            ],
        ];
        $filas = [
            ['id' => 3, 'texto_consulta' => 'x', 'intencion_detectada' => 'recomendar_sustituto', 'confianza' => 0.8123, 'util' => 0, 'creado_en' => '2026-01-01T00:00:00Z'],
            ['id' => 4, 'texto_consulta' => 'hola', 'intencion_detectada' => null, 'confianza' => null, 'util' => null, 'creado_en' => '2026-01-01T00:00:00Z'],
        ];

        $out = ConsultasAsistenteListado::armar($this->db, $filas);

        $this->assertSame('recomendar_sustituto', $out[0]['intencion_detectada']);
        $this->assertEquals((object) ['marca' => 'Toyota', 'codigo' => 'BR-100'], $out[0]['entidades']);
        $this->assertSame(0.875, $out[0]['sugerencias'][0]['similitud']);
        $this->assertNull($out[0]['sugerencias'][1]['similitud']);
        $this->assertTrue($out[0]['sugerencias'][0]['es_sustituto']);

        // Contrato anterior de exportar_feedback.py: respuesta_json.confianza e intencion_detectada.
        $respuestaJson = json_decode($out[0]['respuesta_json'], true);
        $this->assertSame(0.8123, $respuestaJson['confianza']);
        $this->assertSame(['marca' => 'Toyota', 'codigo' => 'BR-100'], json_decode($out[0]['entidades_json'], true));
        $this->assertSame(0.8123, $out[0]['confianza']);

        // Sin hijos: entidades vacías ({}), sin sugerencias.
        $this->assertSame('{}', $out[1]['entidades_json']);
        $this->assertSame([], $out[1]['sugerencias']);
        $this->assertNull($out[1]['confianza']);
    }

    public function testElListadoVacioNoConsultaLasTablasHijas(): void
    {
        $this->assertSame([], ConsultasAsistenteListado::armar($this->db, []));
        $this->assertSame([], $this->db->eventos);
    }
}
