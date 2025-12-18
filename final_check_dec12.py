"""
Verificación final: ¿Es CRT de Revisión el 12 de diciembre?
"""

print("="*70)
print("VERIFICACION FINAL - 12 DE DICIEMBRE 2025")
print("="*70)
print()

# Datos de las velas
candle_1am = {
    'high': 1.17434,
    'low': 1.17268,
    'open': 1.17386,
    'close': 1.17328
}

candle_5am = {
    'high': 1.17352,
    'low': 1.17195,
    'open': 1.17327,
    'close': 1.17274
}

# Calcular cuerpos
candle_1am_body_top = max(candle_1am['open'], candle_1am['close'])
candle_1am_body_bottom = min(candle_1am['open'], candle_1am['close'])

candle_5am_body_top = max(candle_5am['open'], candle_5am['close'])
candle_5am_body_bottom = min(candle_5am['open'], candle_5am['close'])

print("VELA 1 AM:")
print(f"   HIGH: {candle_1am['high']:.5f}")
print(f"   LOW: {candle_1am['low']:.5f}")
print(f"   Cuerpo: {candle_1am_body_bottom:.5f} - {candle_1am_body_top:.5f}")

print("\nVELA 5 AM:")
print(f"   HIGH: {candle_5am['high']:.5f}")
print(f"   LOW: {candle_5am['low']:.5f}")
print(f"   CLOSE: {candle_5am['close']:.5f}")
print(f"   Cuerpo: {candle_5am_body_bottom:.5f} - {candle_5am_body_top:.5f}")

print()
print("="*70)
print("VERIFICACION CRT DE CONTINUACION:")
print("="*70)

# Verificar barrido
swept_low = candle_5am['low'] < candle_1am['low']
close_outside_below = candle_5am['close'] < candle_1am['low']
close_inside_range = candle_1am['low'] <= candle_5am['close'] <= candle_1am['high']

print(f"Barrio LOW: {swept_low} ({candle_5am['low']:.5f} < {candle_1am['low']:.5f})")
print(f"Close FUERA (debajo): {close_outside_below} ({candle_5am['close']:.5f} < {candle_1am['low']:.5f})")
print(f"Close DENTRO: {close_inside_range}")

if not close_outside_below:
    print("\n>>> NO ES CRT DE CONTINUACION")
    print("   El CLOSE de vela 5 AM debe estar FUERA del rango de vela 1 AM")

print()
print("="*70)
print("VERIFICACION CRT DE REVISION:")
print("="*70)

# Para CRT de Revisión: cuerpo debe cerrar DENTRO del rango del cuerpo
body_inside_range = (
    candle_5am_body_bottom >= candle_1am_body_bottom and
    candle_5am_body_top <= candle_1am_body_top
)

print(f"Barrio LOW: {swept_low}")
print(f"Cuerpo 5 AM dentro del rango del cuerpo 1 AM: {body_inside_range}")
print(f"   Body Bottom 5 AM ({candle_5am_body_bottom:.5f}) >= Body Bottom 1 AM ({candle_1am_body_bottom:.5f})")
print(f"   Body Top 5 AM ({candle_5am_body_top:.5f}) <= Body Top 1 AM ({candle_1am_body_top:.5f})")

if swept_low and body_inside_range:
    print("\n>>> ES CRT DE REVISION (BEARISH_SWEEP)")
    print(f"   TP: HIGH de vela 1 AM (extremo opuesto) = {candle_1am['high']:.5f}")
elif swept_low and not body_inside_range:
    print("\n>>> NO ES CRT DE REVISION")
    print("   El cuerpo de vela 5 AM no cierra dentro del rango del cuerpo de vela 1 AM")
else:
    print("\n>>> NO SE CUMPLE NINGUN CRT")

print()
print("="*70)
