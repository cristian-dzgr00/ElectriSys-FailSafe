<?php
declare(strict_types=1);

namespace Tests;

use App\services\BusquedaTexto;
use PHPUnit\Framework\TestCase;

final class BusquedaTextoTest extends TestCase
{
    public function testNormalizaMayusculasYTildes(): void
    {
        $this->assertSame('JOSE NUNEZ', BusquedaTexto::normalizar('José Núñez'));
        $this->assertSame('CAMION', BusquedaTexto::normalizar('  camión '));
        $this->assertSame('PINGUINO', BusquedaTexto::normalizar('Pingüino'));
    }

    public function testPatronEnvuelveConComodinesYNormaliza(): void
    {
        $this->assertSame('%CARLOS%', BusquedaTexto::patron('carlos'));
        $this->assertSame('%MUNOZ%', BusquedaTexto::patron(' Muñoz '));
        $this->assertSame('%%', BusquedaTexto::patron(''));
    }

    public function testPatronEscapaLosComodinesDelUsuario(): void
    {
        // Un "%" o "_" tecleado por el usuario es texto literal, no comodín.
        $this->assertSame('%100\%%', BusquedaTexto::patron('100%'));
        $this->assertSame('%A\_B%', BusquedaTexto::patron('a_b'));
    }

    public function testColumnaEnvuelveLaColumnaConLaMismaNormalizacionQueElPatron(): void
    {
        $sql = BusquedaTexto::columna('c.nombre');
        $this->assertStringStartsWith("UPPER(TRANSLATE(c.nombre,", $sql);
        $this->assertStringContainsString("'áéíóúüñÁÉÍÓÚÜÑ'", $sql);
        $this->assertStringContainsString("'aeiouunAEIOUUN')", $sql);
    }

    public function testComoGeneraElLikeCompleto(): void
    {
        $this->assertSame(
            "UPPER(TRANSLATE(email, 'áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunAEIOUUN')) LIKE ? ESCAPE '\\'",
            BusquedaTexto::como('email')
        );
    }
}
