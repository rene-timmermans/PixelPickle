"""Basisaanpassingen (menu Aanpassen en Afbeelding) die al eerder bestonden."""
from .. import imageops as ops
from . import Choice, Int, effect
from .common import blur_rgba


@effect(0x8052, "Helderheid/contrast", [Int("brightness", "Helderheid", -255, 255, 0), Int("contrast", "Contrast", -100, 100, 0)])
def brightness_contrast(a, ctx, brightness, contrast):
    return ops.adj_brightness_contrast(a, brightness / 2.55, contrast)


@effect(0x8054, "Rood/groen/blauw", [Int("red", "Rood %", -100, 100, 0), Int("green", "Groen %", -100, 100, 0),
                                     Int("blue", "Blauw %", -100, 100, 0)])
def rgb(a, ctx, red, green, blue):
    return ops.adj_rgb(a, red, green, blue)


@effect(0x8060, "Niveaus", [Int("black", "Invoer zwart", 0, 254, 0), Int("white", "Invoer wit", 1, 255, 255),
                            Int("gamma", "Gamma × 100", 10, 500, 100)])
def levels(a, ctx, black, white, gamma):
    return ops.adj_levels(a, black, white, gamma)


@effect(0x8063, "Drempel", [Int("level", "Drempel", 1, 255, 128)])
def threshold(a, ctx, level):
    return ops.adj_threshold(a, level)


@effect(0x804a, "Inkleuren", [Int("hue", "Kleurtoon", 0, 255, 21), Int("saturation", "Verzadiging", 0, 255, 128)])
def colorize(a, ctx, hue, saturation):
    return ops.adj_colorize(a, hue * 360 / 256, saturation * 100 / 255)


@effect(0x8076, "Kleurtoon/verzadiging/helderheid", [Int("hue", "Kleurtoon", -180, 180, 0),
                                                      Int("saturation", "Verzadiging", -100, 100, 0),
                                                      Int("lightness", "Helderheid", -100, 100, 0)])
def hsl(a, ctx, hue, saturation, lightness):
    return ops.adj_hsl(a, hue, saturation, lightness)


@effect(0x8089, "Grofkorreligheid toevoegen", [Int("amount", "Ruis %", 0, 100, 10),
                                               Choice("kind", "Type", ["Willekeurig", "Uniform"]),
                                               Choice("mono", "Kleur", ["Kleur", "Monochroom"])])
def add_noise(a, ctx, amount, kind, mono):
    return ops.adj_noise(a, amount, mono)


@effect(0x8066, "Mediaanfilter", [Int("radius", "Straal", 1, 3, 1)])
def median(a, ctx, radius):
    return ops.adj_median(a, max(1, round(radius * ctx.scale)) if ctx.scale < 1 else radius)


@effect(0x8065, "Gemiddeld", [Int("radius", "Straal", 1, 50, 1)])
def average(a, ctx, radius):
    return blur_rgba(a, radius * ctx.scale)


@effect(0x80b5, "Gaussiaanse vervaging", [Int("radius", "Straal", 1, 100, 3)])
def gaussian(a, ctx, radius):
    return blur_rgba(a, radius * ctx.scale)


@effect(0x8083, "Vervagen")
def blur1(a, ctx):
    return blur_rgba(a, 1 * ctx.scale)


@effect(0x8084, "Meer vervagen")
def blur2(a, ctx):
    return blur_rgba(a, 2 * ctx.scale)


@effect(0x8087, "Verzachten")
def soften(a, ctx):
    return blur_rgba(a, 1 * ctx.scale)


@effect(0x8088, "Nog zachter")
def soften_more(a, ctx):
    return blur_rgba(a, 2 * ctx.scale)


@effect(0x8085, "Verscherpen")
def sharpen(a, ctx):
    return ops.adj_sharpen(a, 1, 60)


@effect(0x8086, "Nog scherper")
def sharpen_more(a, ctx):
    return ops.adj_sharpen(a, 1, 140)


@effect(0x809b, "Onscherp masker", [Int("radius", "Straal", 1, 100, 2), Int("amount", "Sterkte", 1, 500, 100),
                                    Int("clip", "Clip", 0, 100, 5)])
def unsharp(a, ctx, radius, amount, clip):
    return ops.adj_unsharp(a, max(1, round(radius * ctx.scale)), amount, clip)


@effect(0x804c, "Aantal niveaus beperken", [Int("levels", "Niveaus", 2, 255, 4)])
def posterize(a, ctx, levels):
    return ops.adj_posterize(a, levels)


@effect(0x804d, "Solariseren", [Int("threshold", "Drempel", 0, 255, 128)])
def solarize(a, ctx, threshold):
    return ops.adj_solarize(a, threshold)


@effect(0x804b, "Negatief")
def negative(a, ctx):
    return ops.adj_invert(a)


@effect(0x8079, "Grijswaarden")
def grayscale(a, ctx):
    return ops.adj_grayscale(a)


@effect(0x808c, "Bosseleren")
def emboss(a, ctx):
    return ops.adj_emboss(a)
