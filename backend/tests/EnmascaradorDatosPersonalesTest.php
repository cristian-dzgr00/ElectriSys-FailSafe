<?php
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;
use App\services\EnmascaradorDatosPersonales;

/**
 * El historial del asistente no debe guardar correos, teléfonos ni cédulas,
 * pero tampoco debe destrozar las consultas legítimas (códigos, años, motor).
 */
class EnmascaradorDatosPersonalesTest extends TestCase
{
    public static function datosPersonales(): array
    {
        return [
            'celular pegado'          => ['llamar al 3001234567 por el filtro', 'llamar al *** por el filtro'],
            'celular con espacios'    => ['cliente 300 123 4567 pide pastillas', 'cliente *** pide pastillas'],
            'celular con prefijo'     => ['whatsapp +57 300-123-4567 ok', 'whatsapp *** ok'],
            'cedula con puntos'       => ['cedula 1.234.567.890 del cliente', 'cedula *** del cliente'],
            'cedula de 8 digitos'     => ['cc 12345678', 'cc ***'],
            'siete digitos exactos'   => ['tel 5551234', 'tel ***'],
            'correo'                  => ['mandar a juan.perez@correo.com gracias', 'mandar a *** gracias'],
            'correo con subdominio'   => ['ana_r+pos@mail.empresa.co.uk', '***'],
            'varios datos'            => ['juan@x.com y 3001234567', '*** y ***'],
        ];
    }

    #[DataProvider('datosPersonales')]
    public function testEnmascaraDatosPersonales(string $entrada, string $esperado): void
    {
        $this->assertSame($esperado, EnmascaradorDatosPersonales::enmascarar($entrada));
        $this->assertTrue(EnmascaradorDatosPersonales::contiene($entrada));
    }

    public static function consultasLegitimas(): array
    {
        return [
            'consulta del enunciado'  => ['No hay filtro de aceite para Toyota Hilux 2.7 gasolina 2024, ¿qué recomiendo?'],
            'codigo con letras'       => ['cuantas unidades hay del filtro 90915-YZZD4'],
            'codigo corto'            => ['precio del M1-102'],
            'seis digitos'            => ['codigo 123456'],
            'anio y motor'            => ['pastillas corolla 1.8 2015 2019'],
            'rango de anios'          => ['hilux 2015 2019'],
            'rango con guion'         => ['hilux 2015-2022'],
            'cantidad y precio chico' => ['quiero 20 unidades a 35000'],
            'texto vacio'             => [''],
            'solo emojis y tildes'    => ['¿Tienen batería de 12 V? ñandú'],
        ];
    }

    #[DataProvider('consultasLegitimas')]
    public function testNoTocaConsultasLegitimas(string $texto): void
    {
        $this->assertSame($texto, EnmascaradorDatosPersonales::enmascarar($texto));
        $this->assertFalse(EnmascaradorDatosPersonales::contiene($texto));
    }

    public function testUnCodigoDeSoloDigitosLargoSeEnmascaraPorSeguridad(): void
    {
        // Falla hacia enmascarar de más: es solo el registro, la búsqueda usa el texto original.
        $this->assertSame('stock del ***', EnmascaradorDatosPersonales::enmascarar('stock del 7701234567890'));
    }

    public function testNoRompeConTextoMuyLargo(): void
    {
        $largo = str_repeat('filtro de aceite 3001234567 ', 5000);
        $salida = EnmascaradorDatosPersonales::enmascarar($largo);
        $this->assertStringNotContainsString('3001234567', $salida);
        $this->assertStringContainsString('filtro de aceite', $salida);
    }

    public function testNoRompeConUtf8Invalido(): void
    {
        $roto = "filtro \xC3\x28 3001234567";
        $salida = EnmascaradorDatosPersonales::enmascarar($roto);
        $this->assertStringContainsString('***', $salida);
        $this->assertStringNotContainsString('3001234567', $salida);
    }

    public function testEnmascararEstructuraSoloTocaTextos(): void
    {
        $respuesta = [
            'intencion'  => 'consultar_stock',
            'entidades'  => ['codigo' => '7701234567890', 'anio' => 2024, 'motor' => '2.7'],
            'sugerencias' => [['id' => 5, 'precio_venta' => 42000.5, 'nombre' => 'Filtro', 'activo' => true, 'nota' => null]],
            'respuesta_texto' => 'escribe a cliente@correo.com',
        ];
        $salida = EnmascaradorDatosPersonales::enmascararEstructura($respuesta);

        $this->assertSame('***', $salida['entidades']['codigo']);
        $this->assertSame(2024, $salida['entidades']['anio']);
        $this->assertSame(42000.5, $salida['sugerencias'][0]['precio_venta']);
        $this->assertTrue($salida['sugerencias'][0]['activo']);
        $this->assertNull($salida['sugerencias'][0]['nota']);
        $this->assertSame('escribe a ***', $salida['respuesta_texto']);
    }
}
