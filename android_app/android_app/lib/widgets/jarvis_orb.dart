import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../config/app_config.dart';

enum JarvisOrbState { idle, listening, thinking, speaking }

class DotGridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF132536)
      ..style = PaintingStyle.fill;

    const spacing = 14.0;
    for (double y = 0; y < size.height; y += spacing) {
      for (double x = 0; x < size.width; x += spacing) {
        canvas.drawCircle(Offset(x, y), 1.0, paint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class JarvisOrb extends StatefulWidget {
  final JarvisOrbState state;
  final double size;
  final VoidCallback? onTap;

  const JarvisOrb({
    super.key,
    required this.state,
    this.size = 290,
    this.onTap,
  });

  @override
  State<JarvisOrb> createState() => _JarvisOrbState();
}

class _JarvisOrbState extends State<JarvisOrb> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 12),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  String get _statusLabel {
    switch (widget.state) {
      case JarvisOrbState.idle:
        return 'A W A I T I N G   C O M M A N D';
      case JarvisOrbState.listening:
        return 'L I S T E N I N G . . .';
      case JarvisOrbState.thinking:
        return 'P R O C E S S I N G . . .';
      case JarvisOrbState.speaking:
        return 'S P E A K I N G . . .';
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.onTap,
      child: SizedBox(
        width: widget.size,
        height: widget.size,
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, _) {
            final t = _controller.value;
            final speed = widget.state == JarvisOrbState.idle ? 1.0 : 2.5;
            final pulse = 0.5 + 0.5 * math.sin(t * 2 * math.pi * speed);

            return Stack(
              alignment: Alignment.center,
              children: [
                CustomPaint(
                  size: Size(widget.size, widget.size),
                  painter: _OrbPainter(
                    progress: t,
                    pulse: pulse,
                    state: widget.state,
                  ),
                ),
                Positioned(
                  bottom: widget.size * 0.16,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'J A R V I S',
                        style: TextStyle(
                          color: AppConfig.textPrimary,
                          fontSize: widget.size * 0.055,
                          fontWeight: FontWeight.w500,
                          letterSpacing: 4.5,
                        ),
                      ),
                      const SizedBox(height: 5),
                      Text(
                        _statusLabel,
                        style: TextStyle(
                          color: widget.state == JarvisOrbState.idle
                              ? AppConfig.textMuted
                              : AppConfig.cyanPrimary,
                          fontSize: widget.size * 0.032,
                          letterSpacing: 1.8,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _OrbPainter extends CustomPainter {
  final double progress;
  final double pulse;
  final JarvisOrbState state;

  _OrbPainter({
    required this.progress,
    required this.pulse,
    required this.state,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final maxRadius = size.width * 0.47;

    final activeBoost = state == JarvisOrbState.idle ? 0.0 : 0.18 * pulse;
    final coreRadius = maxRadius * (0.28 + activeBoost * 0.25);

    final ambientPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          AppConfig.cyanPrimary.withAlpha(65 + (pulse * 25).round()),
          AppConfig.cyanGlow.withAlpha(24),
          Colors.transparent,
        ],
        stops: const [0.1, 0.55, 1.0],
      ).createShader(Rect.fromCircle(center: center, radius: maxRadius));
    canvas.drawCircle(center, maxRadius, ambientPaint);

    final ringRadii = [maxRadius * 0.52, maxRadius * 0.74, maxRadius * 0.96];
    for (int i = 0; i < ringRadii.length; i++) {
      final r = ringRadii[i];
      final ringPaint = Paint()
        ..color = AppConfig.cyanPrimary.withAlpha(i == 2 ? 75 : 55)
        ..style = PaintingStyle.stroke
        ..strokeWidth = i == 0 ? 1.3 : 1.0;
      canvas.drawCircle(center, r, ringPaint);
    }

    final arcPaint = Paint()
      ..color = AppConfig.cyanPrimary.withAlpha(150)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.8
      ..strokeCap = StrokeCap.round;
    final startAngle = progress * 2 * math.pi;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: ringRadii[1]),
      startAngle,
      math.pi * 0.45,
      false,
      arcPaint,
    );

    final dots = <List<double>>[
      [ringRadii[0], progress * 2 * math.pi + 2.6, 3.2],
      [ringRadii[1], -progress * 2 * math.pi + 3.4, 3.8],
      [ringRadii[1], progress * 2 * math.pi + 0.9, 3.2],
      [ringRadii[2], progress * 2 * math.pi + 1.1, 4.0],
      [ringRadii[2], -progress * 2 * math.pi + 5.1, 2.8],
    ];
    for (final dot in dots) {
      final r = dot[0];
      final angle = dot[1];
      final radius = dot[2];
      final pos = Offset(
        center.dx + r * math.cos(angle),
        center.dy + r * math.sin(angle),
      );
      canvas.drawCircle(
        pos,
        radius * 2.1,
        Paint()..color = AppConfig.cyanPrimary.withAlpha(55),
      );
      canvas.drawCircle(
        pos,
        radius,
        Paint()..color = AppConfig.cyanPrimary,
      );
    }

    canvas.drawCircle(
      center,
      coreRadius * 1.38,
      Paint()..color = const Color(0xFF041422).withAlpha(220),
    );

    final coreShader = RadialGradient(
      colors: [
        Colors.white,
        AppConfig.cyanPrimary,
        AppConfig.cyanGlow.withAlpha(190),
        Colors.transparent,
      ],
      stops: const [0.0, 0.28, 0.68, 1.0],
    ).createShader(Rect.fromCircle(center: center, radius: coreRadius * 1.25));
    canvas.drawCircle(center, coreRadius * 1.25, Paint()..shader = coreShader);

    canvas.drawCircle(
      center,
      coreRadius * 0.85,
      Paint()
        ..color = AppConfig.textPrimary.withAlpha(140)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.0,
    );
  }

  @override
  bool shouldRepaint(covariant _OrbPainter oldDelegate) => true;
}