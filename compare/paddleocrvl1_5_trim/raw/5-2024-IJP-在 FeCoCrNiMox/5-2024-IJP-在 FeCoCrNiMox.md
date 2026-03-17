International Journal 0l Plasticity 183 (2024) 104142
ISSN 0745-G419
INTERNATIONAL JOURNAL OF
asticitu
International Journal of Plasticity
Multiscale plastic deformation in additively manufactured
FeCoCrNiMox high-entropy alloys to achieve strengthductility
synergy at elevated temperatures
Danyang Lin a, Jixu Hu a, Renhao Wu b,*", Yazhou Liu a,d, Xiaoqing Lic,
Man Jae SaGong b, Caiwang Tan a, Xiaoguo Song a,*, Hyoung Seop Kim
b,d,e,f,*
a State Key Laboratory of Precision Welding & Joining of Materials and Structures, Harbin Institute of Technology, Harbin 150001, China
b
Graduate Institute of Ferrous & Eco Materials Technology, Pohang University of Science & Technology, Pohang 37673, Korea
c Department of Materials Science and Engineering, Applied Materials Physics, KTH - Royal Institute of Technology, Stockholm SE-10044, Sweden
d Department of Materials Science & Engineering, Pohang University of Science & Technology, Pohang 37673, Korea
e Advanced Institute for Materials Research (WPI-AIMR), Tohoku University, Sendai 980-8577, Japan
f
Institute for Convergence Research and Education in Advanced Technology, Yonsei University, Seoul 03722, South Korea

## ARTICLE INFO

## ABSTRACT

## Keywords

The application of structural metals in extreme environments necessitates materials with superior
Additively manufactured FeCoCrNiMox
mechanical properties. Mo-doped FeCoCrNi high-entropy alloys (HEAs) have emerged as po-
Multiscale plastic deformation
tential candidates for use in such demanding environments. This study investigates the high-
Deformation twinning
temperature performance of FeCoCrNiMox HEAs with varying Mo contents (x = 0, 0.1, 0.3,
Molecular dynamics simulation
and 0.5) prepared by laser powder bed fusion additive manufacturing. The mechanical properties
Elevated temperature
were evaluated at room and 600 C temperatures, and the microstructures were characterized
using scanning electron microscopy, electron backscatter diffraction, energy dispersive X-ray
spectroscopy, and transmission electron microscopy. The intrinsic dislocation cell patterning,
solid-solution strengthening, nanoprecipitation, and twinning effects collectively modulated the
plastic deformation behavior of the samples. The high-temperature mechanical performance was
comprehensively analyzed in conjunction with ab initio calculations and molecular dynamics
simulations to reveal the origin of the experimentally observed strengthductility synergy of
FeCoCrNiMoo.3. This study has significant implications for FeCoCrNiMox HEAs and extends our
understanding of the structural origins of the exceptional mechanical properties of additively
manufactured HEAs.

## 1. Introduction

The pursuit of advanced structural metals that perform reliably in high-temperature environments remains a challenge. High-
*
Corresponding authors.
https://doi.org/10.1016/j.ijplas.2024.104142

2015).
However, despite the satisfactory mechanical properties of single-phase FeCoCrNi-based HEAs at room and low temperatures
(Gludovatz et al., 2014; Kuzminova et al., 2021; Liu et al., 2017), the high-temperature mechanical performance requires further
improvement. For instance, Liao et al. (2023) explored the compression behavior of equimolar FeCoCrNi HEAs, and noticed a softening
effect at elevated temperatures owing to increased grain boundary migration and thermal activation of the matrix. This pronounced
softening effect significantly reduces the strength and plasticity of FeCoCrNi-based HEAs at 600 C (Lin et al., 2022). During defor-
mation, nanoclusters cause cracks to form at the grain boundaries, leading to a loss of ductility at high temperatures. Similarly, the
high-temperature tensile properties of FeCoCrNiMn show evident softening at 600700 C, resulting in poor performance at high
temperatures (Jo et al., 2022; Sun et al., 2022).
To enhance the high-temperature mechanical properties of HEAs, significant progress has been made in controlling precipitation
(Yang et al., 2020) and alloying-element segregation at grain boundaries (Hou et al., 2022). Gan et al. (2024) introduced D022
nanoparticles into an FCC HEA, which increased the dislocation storage capability and strain hardening, greatly improving the tensile
properties in the 600700 °C range. Researchers have also achieved improvements in strength and plasticity at 750 C by doping the
FCC matrix with elements such as Ti, Nb, Ta, Mo, and W to reduce the SFE and introduce nanoscale L12 precipitates, resulting in
various work-hardening behaviors (Gao et al., 2024). Therefore, adding trace elements and introducing nanoscale precipitates into the
FCC matrix is a promising strategy for improving the high-temperature performance.
The addition of medium-atomic-size Mo to the FeCoCrNi matrix can induce precipitation strengthening in the solid-solution FCC
phase and even trigger a eutectic precipitation reaction (Guo et al., 2020). Consequently, Mo-doped FeCoCrNi HEAs exhibit enhanced
mechanical properties, including good wear resistance (Fan et al., 2024), corrosion resistance (Dai et al., 2020; Yen et al., 2024), and
biocompatibility (Hiyama et al., 2024). By controlling the Mo content, phase selection can be achieved to alter the structure and
properties of the HEAs, which is crucial for regulating the performance.
Dai et al. (2021) reported the effect of grain size on the mechanical properties of FeCoCrNiMoo.1. The mechanical performance at
energy, and the matrix and precipitate phases segregate during deformation at elevated temperatures (Wu et al., 2018). The enhanced
slip reversibility is attributed to improved slip planarity owing to the addition of Mo, which results in a decreased SFE and increased
lattice friction stress and shear modulus. Moreover, the stacking-fault-mediated deformation mechanism in FeCoCrNiMo.2 helps to
inhibit fatigue-induced plastic deformation (Li et al., 2019). Cai et al. (2017) discovered that Mo-rich intermetallic compounds pre-
cipitate in FeCoCrNiMoo.23 upon annealing. However, the bonding force between the intermetallic compounds and matrix is weak, and
the probability of stacking faults is reduced, thus suppressing the formation of deformation twins and resulting in a tradeoff between
strength and ductility. Liu et al. (2016) found that in FeCoCrNiMoo.3, the precipitation of hard σ and µ phases greatly strengthens the
material (tensile strength of up to 1.2 GPa) without causing severe embrittlement. Shun et al. (2012) reported that with an increase in
the Mo content in cast FeCoCrNiMox, the strength increases, whereas the plasticity decreases. Aged FeCoCrNiMoo.85 has a higher
hardness than aged FeCoCrNiMoo.3 and FeCoCrNiMoo.5 owing to the precipitation of a larger volume fraction of hard needle-like σ
considering the effect of temperature in detail. In particular, few studies have evaluated the high-temperature mechanical properties
and microstructural evolution of FeCoCrNiMox HEAs (Li et al., 2022; Wang et al., 2017), and systematic and in-depth studies on the
Laser-based additive manufacturing (L-AM) is an advanced precision manufacturing technique that facilitates high-throughput
fabrication and offers significant opportunities for in situ materials design with tailored microstructures (Li et al., 2022). An et al.
(2023) revealed that L-AM-processed FCC metals have hierarchical microstructures that exhibit several plastic deformation mecha-
nisms, thereby enhancing the mechanical performance compared with conventionally fabricated counterparts. Notably, the unique
dislocation cell patterns, which are caused by residual stresses arising from the large temperature gradient and thermal cycling during
L-AM, significantly contribute to the strength (He et al., 2022; Kwon et al., 2022). Sui et al. (2022) investigated L-AM-processed
FeCoCrNiMo and reported that its hierarchical eutectic and irregular lamellar structures resulted in high hardness and wear resistance.
Furthermore, in our previous work, we demonstrated the capability of L-AM for fabricating FeCoCrNiMox (x = 0.3 and 0.5) HEAs with
good mechanical properties (Lin et al., 2024, 2023). Deformation twinning and micro/nanoprecipitates such as σ phases were
observed when the Mo fraction exceeded 0.3.
In this study, we utilized laser powder bed fusion (L-PBF) additive manufacturing to fabricate a series of defect-free FeCoCrNiMox
HEAs with varying Mo contents (x = 0, 0.1, 0.3, and 0.5). The mechanical properties and microstructural evolution were systematically
investigated at room and elevated temperatures. The thermal stability and uniaxial tensile deformation behavior were studied by
electron backscatter diffraction (EBSD) and transmission electron microscopy (TEM). Additionally, ab initio calculations and molecular
strength.

dynamics (MD) simulation models were established to quantify changes in the microscale lattice strain and stacking fault probability
associated with plastic deformation. This work provides a quantitative assessment of the effects of the hierarchical microstructure on
mance as structural materials.

## 2. Materials and methods

## 2.1. Powder preparation and L-PBF process

To fabricate the FeCoCrNiMox HEAs (x = 0, 0.1, 0.3, and 0.5; Mo content = 0, 2.44, 6.98, and 11.11 at%, respectively), denoted as
Mo0, Mo1, Mo3, and Mo5, respectively, equiatomic FeCoCrNi and FeCoCrNiMo powders with spherical particles (diameter: 1553 µm)
were produced by gas atomization. The powders were then mixed at different molar ratios in a three-dimensional mixer at 40 rpm for 5
h under a protective Ar atmosphere (Fig. 1a). Next, L-PBF was conducted using a RENISHAW AM-400 platform with a preheating
temperature of 120 C. The processing parameters were as follows: bidirectional scanning speed, 750 mm/s; laser power, 200 W; hatch
spacing, 80 µm (Mo0, Mo1, and Mo3) or 70 µm (Mo5); layer thickness, 40 µm; and rotation between layers, 67°. Blocks with
a
FeCoCrNiMo
FeCoCrNi
+
100μm
Co
Cr
Mo
C
Mo0
Mo3
Mo5
Mo1
Co
Cr
Fe
Ni
Mo
b
Laser
c
4.5
N+1 layer
R6
N layer
φ5
Z (BD)
M8
y
x
Unit: mm
Fig. 1. L-PBF additive manufacturing procedures and prepared samples for tensile tests: (a) different Mo content ratios are achieved by adjusting
he ratio of FeCoCrNi and FeCoCrNiMo powders, (b) Schematic diagram of L-PBF process, (c) Size of tensile specimen at room temperature (dog-
pone shape) and high temperature (600 °C, round rod shape).

dimensions of 80 × 40 × 20 mm were fabricated (Fig. 1b).

## 2.2. Mechanical testing

speed of 0.5 mm/min (initial strain rate: ~3 × 10-4 s−1).

## 2.3. Microstructural characterization

evolution of Mo5 was characterized by SEM, EBSD, EDS, and TEM.

## 2.4. Ab initio calculations and molecular dynamics (MD) simulations

Ab initio calculations were conducted using density functional theory (DFT) (Hohenberg and Kohn, 1964), employing the exact
muffin-tin orbitals method to solve the KohnSham equations (Andersen et al., 1995; Vitos, 2001; Vitos et al., 2000). The Per-
dew-Burke—Ernzerhof exchangecorrelation functional was used for self-consistent determination of the charge density and total
energy (Perdew et al., 1996). Given that the magnetic ordering temperature of FeCoCrNi is well below room temperature, all
spin-polarized DFT calculations were performed assuming a paramagnetic state (Gyorffy et al., 1985). The paramagnetic state was
described using a disordered local moment approach. The coherent potential approximation was employed to model the chemical
disorder (Gyorffy, 1972; Vitos et al., 2001).
For SFE calculations, we followed the methodology described by Schönecker et al. (Schönecker et al., 2021). The thermal lattice
expansion and magnetic contributions were considered to account for the temperature dependence of the SFE. Specifically, we derived
the lattice expansion of the FCC phase by minimizing the free energy F(V, T) = EPM(V) TSPM(V) + Fvib(V, T) over the atomic volume V
PM
for a given temperature T, where I
and
are the total energy and magnetic entropy of the paramagnetic state, respectively, and
a 1200
b 1200
25°
—Mo0
—Mo0
Engineering strength, MPa
Mol
Engineering strength, MPa
Mol
Mo3
Mo5
Engineering strain, %
c 10000
d
a
Mo3 25°C
This work
Mo0
Mo1 Mo3 Mo5
Strength-ductility
Mo5 25°C
Ultimate tensile strength, MPa
trade off
VIM FeCoCrNi
LPBF FeCoCrNiMn
Work hardening rate, MPa
Mo5
VIM FeCoCrNiMn
Mo3 600°
o
LPBF FeCoCrNi
VIM FeCoCrNiZr0.4
LPBF NiAlqCr12C06
Mo5 600°
D
VIM FeCoCrNiAle.1
Ni22Cr9Mo
LPBF
VIM AICrNbTiVZr
3Fe4Nb
Mo3
VIM AlCoCrCuFeNi
Ti6Al2Zr
Mo1
LPBF
EBM Inconel 718
1Mo1V
Mo0
a
EBAM
Ti5Al2Sn
a
VIM Inconel 718
2Zr4Mo4Cr
LPBF Inconel 718
EPBF
Ti2AINb
I
Roll Inconel 600
I
LPBF
Ti2AINb
I
VIM TiAl
U
LPBF Ti6AI4V
0.05
0.1
0.15
0.2
0.25
0.3
True strain
Uniform elongation, %
alloys (References for these data are given in the Supplementary Materials).

1988). S
PM
magnetic moments (Grimvall, 1975).
potential function used is the modified embedded atom method (MEAM) potential for six elements (Ni-Cr-Co-Mo-V-Al) developed by
Wang et al. (2023), and it is incorporated into the HEA model's machine learning through a neural network. Liu et al. (2024) and (Shi
et al., 2024) respectively used this potential function to verify the deformation mechanisms of medium entropy alloy (MEA) and HEAs,
achieving ideal results. The uniaxial tensile simulations of the single crystal nanowire are conducted at two temperatures: 25 C and
To obtain atomic models with random elements distribution, we first conducted energy minimization on the initial models, fol-
lowed by relaxation for 20 ps at 25 C. Using a combination of MC atom swaps and MD hybrid method, we constructed atomic models
for alloy containing CSRO based on the initial models. After MC simulation, we annealed the model from 1227 C to 25 °C and 600 °C at
a 1 °C/ps rate. For a second lattice relaxation under canonical ensemble (NVT), we switched the model to non-periodic boundary
conditions on the x, y, and z axes. The y-direction deformation is performed at an engineering strain rate of 2 × 108 s1. At the top and
bottom regions of the simulation box, rigid blocks containing immobile atoms were positioned. A constant velocity was applied to
these blocks in opposite directions to deform the model. Free boundary conditions were established on the planes parallel to the
loading axis. During the tensile process, velocity rescaling was performed at every step. While this may influence the thermal con-
ductivity analysis of HEAs, both the literature (Chen et al. 2021) and our research (Liu et al. 2024) indicate that this approach stabilizes
the deformation temperature, with negligible impact on deformation twinning. We compared velocity rescaling every 1, 5, 10, and 100
steps, as well as a case with no rescaling. The lack of thermal energy in the system does not significantly affect the MD simulation
results.
In the simulation process, the strain rate is actually 108109s1.(Chen et al., 2021; Liu et al., 2024) This calculation speed is closer
to the experimental results in macroscopic experiments, although there is a large gap between the calculation speed and the actual
speed. However, due to the effects of size effects, etc., it is possible to qualitatively analyze the deformation mechanism.

## 3. Results and discussion

## 3.1. Mechanical properties

Figs. 2a and 2b show the uniaxial tensile stressstrain curves of the as-built L-PBF-processed samples with varying Mo contents
(Mo0, Mo1, Mo3, and Mo5) at temperatures of 25 and 600 C. At room temperature, Mo enhances both the strength and ductility
(Table 1). Compared with Mo0, the yield strength (YS) of Mo1 increases from 566 to 609 MPa and the ductility increases from 19% to
27%. Mo3 and Mo5 exhibit even higher room-temperature mechanical properties.
The mechanical performance of all samples decreases significantly at elevated temperatures, with their YS and ultimate tensile
strength (UTS) varying considerably. The ductility of Mo0 is less than 10%, indicating its unsuitability for high-temperature appli-
cations. Mo1 displays dynamic strain strengthening during high-temperature tensile loading; however, its ductility is still less than
10%. A notable disparity is observed in the high-temperature tensile performance of Mo3 and Mo5. For Mo3, the YS, UTS, and uniform
elongation at 600 C are 20%, 57%, and 1513% higher, respectively, than those of Mo0. The strain hardening of Mo3 is essentially the
same as that at room temperature (Fig. 2c). Consequently, it demonstrates a successful balance between strength and ductility at high
temperatures. By contrast, the ductility of Mo5 approaches the lower limit of the acceptable range (10%).
At 600 C, Mo1 exhibited significant serrated flow behavior, whereas Mo0, Mo3, and Mo5 did not show this phenomenon at this
temperature. It can be seen that at the same temperature, serrated flow behavior is closely related to the Mo content. The essence of
serrated flow is the pinning effect of solute atom clusters on dislocations, which increases the flow stress. When the flow stress increases
to a certain value, the dislocations break through the solute clusters, causing a sudden drop in flow stress. These two actions alternate,
forming the serrated flow behavior. In Mo0, no Mo element was added, and the structure contains only Fe, Co, Cr, and Ni elements,
with atomic radii of 124.1, 125.3, 124.9, and 124.6 Å, respectively. Since the atomic diameters are relatively close, the lattice
distortion effect is not significant, and the pinning effect of solute atoms on dislocation motion is low. Thus, no serrated flow behavior
occurs. In Mo1, Mo atoms (with a diameter of 136.3 Å) aggregate into solute clusters near dislocations, significantly increasing the
Table 1
Summary of mechanical properties of the L-PBF additively manufactured FeCoCrNiMox (x = 0, 0.1, 0.3, and 0.5) HEAs at different temperature
conditions.
Sample
Temperature, C
YS, MPa
UTS, MPa
UFE, %
TE, %
Mo0
18.15
19.82
1.20
1.25
Mo1
27.46
36.51
6.71
8.23
Mo3
25.02
27.78
19.35
22.98
Mo5
19.38
19.93
11.16
11.33

around dislocations, thereby eliminating serrated flow behavior.
grain boundaries. Therefore, the addition of Mo in Mo1 and Mo3 improves the bonding strength at the grain boundaries, enhancing
high-temperature plasticity. The slight decrease in plasticity of Mo5 compared to Mo3 is due to the embrittlement caused by the
growth of the σ phase.
Fig. 2d compares the high-temperature (>600 °C) mechanical properties of various FeCoCrNi-based HEAs, Ti-based alloys, and Ni-
based superalloys. Mo3 and Mo5 exhibit comparatively remarkable mechanical performance, particularly regarding the
strengthductility trade-off. This advancement demonstrates the potential of these alloys for use in high-temperature environments.

## 3.2. Initial microstructures of L-PBF-processed FeCoCrNiMox HEAs

For a more comprehensive understanding of the reasons behind the changes in performance, we conducted a detailed micro-
structural analysis. Fig. 3 presents SEM images of the additively manufactured FeCoCrNiMox HEAs. The samples are nearly defect-free,
although a few small round pores (<1 µm) are visible near the fusion lines. Moreover, a distinct dendritic structure is concentrated at
the overlaps of the melt pools, with clear dendrite and interdendrite regions (Figs. 3a, 3b, and 3c, insets). In comparison with Mo0
(Fig. 3a), the Mo-containing samples exhibit sharper dendrites (Figs. 3b and 3c). Because of the significant temperature gradient and
thermal cycling during L-PBF, the initial solidification occurs faster at the top of the molten pool than at the bottom (Hu et al., 2022;
Munusamy and Jerald, 2023; Wang et al., 2023b). This results in dendritic growth at the top of the pool, whereas the bottom maintains
planar crystal growth. Small grains form in the intersecting areas of the melt pools (Fig. 3d, inset). Therefore, the additively manu-
factured FeCoCrNiMox HEAs exhibit microstructural heterogeneity, with a grain size distribution of a few microns to tens of microns.
Fig. 4 presents the EBSD results of the as-built FeCoCrNiMox HEAs. From the inverse pole figure maps, the Mo0 grains show a clear
tendency to grow along the direction of construction (z direction). This is attributed to the thermal gradient and optimal solidification
orientation (Körner et al., 2020). Thus, the grains have a unidirectional epitaxial columnar shape. In addition, the matrix exhibits a
relatively obvious 100<111> texture, as illustrated in the pole figure in Fig. 4a3. However, the introduction of Mo induces notable
changes (Figs. 4b1, 4c1, and 4d1), with a more random grain orientation. Furthermore, the average grain size increases from 35.1 µm
for Mo0 to 57.5 µm for Mo3. Given that Mo is a refractory element, a higher energy density is required for preparation. Therefore, the
Mo0
Mo1
b
a
E
L
20μm
Mo
M05
c
d
grain
2μm
Gas pore
L
Fusion line

Mo0
Mo1
Mo3
Mo5
a1
b1
Jum
100μm
a2
GND=8.45×1014/m2
b2
GND=9.84×1014/m2
c2
GND=8.25×1014/m2
d2
GND=8.99×1014/m²
a3
b3 3
c3 3
d3
Avg. = 47.4μm
Avg.
57.5μm
2.5
X0
Fraction, %
Fraction, %
1.5
{100}
{110}
YO
Min=0
0.5
O
Recrystallized
6.4%
M
A
H
A
A
Substructured
69.4%
Size, μm
{111}
Size, μm
Deformed
24.2%
Max=8.5
Fig. 4. Typical microstructure of L-PBFed samples: (a1-a3) Mo0, (b1-b3) Mo1, (c1-c3) Mo3, and (d1-d3) Mo5. (a1, b1, c1, d1) EBSD inverse pole
figure (IPF) maps showing the grain size and morphology. (a2, b2, c2, d2) KAM images superimposed with high angle grain boundaries (HAGBs,
black lines). (a3) Texture orientation of Mo showing 100<111>; (b3, c3) Statistics for the grain size; (d3) Distribution of grain state in recrystallized,
substructured, and deformed.
Table 2
Summary of microstructural characteristics of the as-built FeCoCrNiMox HEAs (x = 0,0.1,0.3, and 0.5).
Sample
Mo at%
Avg. grain size, µm
GND density, ×1014 /m2
Fraction of RX, %
Texture orientation
Mo0
35.1
8.45
2.9
100<111>
Mo1
2.44
47.4
9.84
13.3
100<111>
Mo3
6.98
57.5
8.25
10.7
100<111>
Mo5
11.11
51.9
8.99
6.4
100<111>
average geometrically necessary dislocation density of Mo3, as calculated from the kernel average misorientation, is similar to that of
Mo0. The microstructural characteristics are summarized in Table 2.
The variations in the grains (orientation, recrystallization, and size) of the FeCoCrNiMox HEAs highlight the complex interplay
between the composition and processing parameters, resulting in differences in the mechanical properties. Overall, the multiscale
heterogeneity is derived from microscale lattice defects (Zhang et al., 2018), requiring more geometrically necessary dislocations to
achieve microstructural deformation during L-PBF. As shown in Fig. 4d3, Mo5 contains a few recrystallized grains, whereas most
grains are substructured and deformed, indicating a high dislocation density. In addition to the high density of dislocation cells caused
by thermal residual stress, slow elemental diffusion within HEAs is also considered to hinder recrystallization (Miracle and Senkov,
2017). The fraction of partially recrystallized grains is affected by the Mo concentration (Ming et al., 2019), as well as laser-induced
structural deformation (Peng et al., 2024)and precipitation (He et al., 2021a). The recrystallized fraction of the FeCoCrNiMox samples
varies from 2.9% to 13.3%, which will affect the dislocation hardening behavior during tensile deformation.
Fig. 5 shows the dislocation morphology and elemental segregation of the FeCoCrNiMox HEAs, as characterized by TEM and EDS.
Laser-printed samples typically exhibit hexagonal dislocation cell patterns because of residual stresses during solidification (He et al.,
2022). However, the dislocation cell patterns are not obvious in Mo0. As the Mo content increases, the dislocation cell features become
more obvious and the cell walls become sharper. The cell wall thickness decreases from approximately 200 nm for Mo1 to 50 nm for
Mo5, and the cell size increases slightly. Some stacking faults can also be observed in Mo5.
Mo3 and Mo5 contain rod-shaped nanoscale σ-phase precipitates at the grain boundaries (Figs. 5c and 5d). This is because Mo, a
refractory metal with a large atomic radius, is likely to be enriched at locations with large lattice distortions, such as grain boundaries,

L-PBF additive manufacturing as-built state
a2
b1
b2
a1
Mo0
Mo1
unit
1μm
c1
c2
d1
d2
~50
Rod-shaped
phase ppts
Mo3
Mo5
SFs
Dislocation
S
cell
1μm
1μm
Fe
Co
Ni
Mo
Co
Ni
Mo
Cr
Fig. 5. TEM image reveals the microstructure of the dislocation networks of the as-built FeCoCrNiMox HEAs: (a) Mo0, (b) Mo1, (c) Mo3, and (d)
Mo5; EDS mapping results of the Cr-rich nano precipitates in rod shape (σ phase) and blocky shape (µ phase) in Mo3 and Mo5 samples. Nano-twins
generate in Mo5 samples inside of the DCP. The white arrows highlight the emission of stacking faults (SFs) with the DCP.
which act as nucleation sites. Segregated Cr/Mo solutes can also redistribute or diffuse into mobile grain boundaries during matrix
growth (He et al., 2021a), thereby promoting σ-phase nucleation along the grain boundaries. The diffusion rate of Mo is much slower
than that of Cr. In addition, it is present in relatively lower concentrations than the other elements in the HEA. Therefore, it is primarily
Cr (He et al., 2021a)that partitions into the σ phase. In addition to the nanoscale σ-phase precipitates, blocky µ-phase precipitates can
also be observed (Cr-rich Mo). The µ-phase precipitates appear at the edges of the σ-phase precipitates, indicating that they may be
generated by transformation of the σ phase during solidification. Sui et al. (Sui et al., 2022) credited µ-phase formation to the lattice
strain produced by excessive Mo, which makes the σ phase unable to maintain its tetragonal structure. The release of lattice strain
Post-necking state after tensile deformation @25°C
a1
a2
b1
b2
Mo1
Mo0
d1
c1
d2
c2
Mo3
Fig. 6. Deformation microstructures evolution of L-PBFed FeCoCrNiMox sample at the post-necking deformation stage under tensile tests at room
temperature is presented. Bright-field and dark-field TEM images reveal the different twinning effects of the FeCoCrNiMox HEAs: (a) Mo0, (b) Mo1,
(c) Mo3, and (d) Mo5.

grain boundaries, which effectively inhibits the formation of Mo-containing alloy through the pinning effect and can effectively delay
recrystallization and grain growth (Linder et al., 2024; Miracle and Senkov, 2017).

## 3.3. Microstructural evolution of FeCoCrNiMox HEAs during deformation at 25 and 600 °C

Fig. 6 shows TEM images of near-neck regions of the samples deformed at room temperature. These images demonstrate the
distinctive role of twinning in the room-temperature plastic deformation of FeCoCrNiMox HEAs. However, there is a notable variation
in the density and width of twins across different samples. Specifically, the presence of twins in the Mo0, Mo1, and Mo3 samples is
more pronounced compared to the Mo5 sample, where the number is relatively small, as shown in Fig. 6d2. This suggests that the
critical stress required for twin activation in the as-built Mo5 sample is significantly higher than the other samples, even though it
exhibits greater strength and ductility than the Mo0 and Mo1 HEAs. This is primarily due to the presence of a significant amount of σ
precipitates (Fig. 5) in Mo5. These precipitates can partially hinder the movement of dislocations, thereby preventing the formation of
stacking faults in the matrix (Cai et al., 2017). Consequently, this reduces the likelihood of stacking faults, and further decreases the
probability of twin formation. Additionally, the significant plastic deformation during the stretching process in Mo3, combined with
the lower quantity of σ precipitates, leads to a much higher number of twins in Mo3 compared to Mo5.
According to Table 1, the strength of Mo0 and Mo1 decreased by 40% at high temperatures, while the ductility of Mo3 and Mo5
only decreased by 30%. Moreover, Mo3 and Mo5 retained a higher percentage of elongation. To understand this difference, we
conducted high-temperature fracture surface TEM analysis. Fig. 7 displays the TEM characterization results of the near-necking po-
sition of samples with different Mo contents after deformation at high temperatures. We observed that due to the lack of precipitates
hindering their movement, the grains in the Mo0 and Mo1 samples were significantly elongated post-deformation. These lamellar grain
boundaries act as strengthening barriers, accumulating intragranular dislocations and consequently reducing the ductility of the
samples. In the Mo3 and Mo5 sample, some cellular dislocations remained visible, and short rod-shaped precipitates of the σ phase
were located on the dislocation cell wall. These precipitates played a pinning role in the movement of the dislocation cell, contributing
to its high-temperature stability. It is worth noting that in the Mo3 and Mo5 samples, the hindrance of dislocation motion by pre-
cipitates results in the accumulation of a large number of dislocations at grain boundaries. This leads to stress concentrations exceeding
the critical twinning stress level, causing the formation of deformation twins. This indicate that in addition to the dislocation coor-
dination deformation observed in Mo0 and Mo1, twinning induced plasticity (TWIP) effects also came into play. Since the deformation
temperature does not reach the secondary precipitation temperature of the σ phase, the ratio of precipitates will not increase further
during the high-temperature deformation process (Elmer et al., 2007). High-density dislocations pile up along the hard σ-phase
precipitates, hindering further dislocation slip. The excessive σ-phase cannot deform coherently with the matrix, leading to cracking
under low plastic deformation conditions. As a result, stress concentration-induced cracking occurs earlier in Mo5 than in Mo3 sample
during tensile deformation.
Post-necking state after tensile deformation @600°C
a1
a2
b1
b2
CB
Mo0
Mo1
1μm
1μm
c1
c2
d1
d2
Rod-shaped σ
phase ppt
Mo3
Twin
Mo5
Rod-shaped σ
Twin
phase ppt
1μm
1μm
(b) Mo1, (c) Mo3, and (d) Mo5. GB: grain boundary.

a1
a2
a3
Mo3
a3
Ta2
2μm
b1
b2
b3
Mo5
Fb21
Y
2μm
Fig. 8. Necking-fracture morphology of (a) Mo3 and (b) Mo5 samples after tensile deformation at 25 °C.

## 3.4. Fracture morphology of Mo3 and Mo5 at 25 and 600 C

To elucidate the fracture mechanisms of the Mo3 and Mo5 samples, we conducted an analysis of the fracture surfaces of the tensile
specimens at 25 C and 600 C. Fig. 8 illustrates the room-temperature fracture morphologies of Mo3 and Mo5. The fracture surfaces
are characteristic of FCC materials, with high densities of tears and dimples. Under uniaxial loading, the initial crack extends in the
tensile direction, forming voids during the crack extension stage. The connections between these voids result in fractures. Some
tongue-shaped pits or protrusions formed by extension of the cleavage cracks along the twin boundaries are visible (Fig. 8b2). This
phenomenon is consistent with the findings of Sui et al. (Sui et al., 2022). Fig. 8a3 indicates that the molten pool boundary is sus-
ceptible to fracture.
Fig. 9 illustrates the high-temperature fracture morphologies of Mo3 and Mo5. The fracture surface of Mo3 still exhibits ductile
fracture characteristics, albeit with a diminished presence of dimples as compared to that at room temperature. The emergence of twins
during the latter stages of deformation renders the fracture surface akin to the room-temperature fracture surface of Mo5, with tongue-
shaped cleavage crack patterns. By contrast, the high-temperature fracture surface of Mo5 exhibits quasi-cleavage traits. Cleavage
steps are formed by fracture along the crystal planes at varying heights. The fracture surface of Mo5 (Fig. 9b2) is considerably flatter
than that of Mo3 (Fig. 9a2), suggesting that the fracture strain was relatively constrained during the tensile process. This observation
aligns with the high-temperature tensile stress—strain curves. The presence of σ-phase precipitates, which are hard and brittle inter-
metallic compounds, enhances the compressive strength but concurrently reduces the fracture strain.
a1
a2
a3
$a2
Mo3
a3
400μm
2μm
b1
b2
b3
T b21
400μm
2µm
(b) Mo5.

mechanical properties of FeCoCrNiMox HEAs.
a
Mo0
Mo1
Mo3
Mo5
Liquid + FCC
Temperature,
Liquid + FCC
Liquid + σ-phase
+ FCC
Liquid + σ-phase + FCC
Liquid + FCC
Liquid + σ-phase
+FCC
0.1
0.2
0.3
0.4
0.5
0.6
0.7
0.8
0.9
Mole fraction of solid phase
b
c
+Co
Mol
Mo5
Cr
Atomic fraction of element, at%
Atomic fraction of element, at%
*
Fe
Mo
Ni
Co
Cr
+ Fe
Mo
Ni
C
:
0.2
0.4
0.6
0.8
0.2
0.4
0.6
0.8
Mole fraction of solid phase
d
Mo0
Mol
Mo3
Mo5
TTTT
TTT
TTTTT
Cell interior
Cell wall
L Dislocation
Nano /μ-phase ppt
Fig. 10. (a) The diagram of the nonequilibrium solidification thermodynamic process and phase evolution of Mo0, Mo1, Mo3 and Mo5 HEAs
parison of printed microstructure characteristics with varying Mo additions.

a
Closed-packed planes
b
Perfect stacking
Intrinsic stacking fault
[112]fcc
[211]fcc
FCC
b
p2
[110]fcc
C
[111]
B
A
[112]
-10
Intrinsic SFE, mJ/m2
-20
-30
-40
-0 at%

## 6. at%

-50
-11 at%
-60
Temperature, K

## 3.5. Solidified phase equilibrium state of FeCoCrNiMox HEAs

The σ-phase is brittle, and therefore, its presence is generally detrimental for long-term applications. However, in this study, the
addition of Mo promoted the precipitation of the σ-phase at grain boundaries, which further hindered cell deformation at high
temperatures. Additionally, the pinning effect suppressed grain boundary migration, enhancing the high-temperature strength and
plasticity of the HEA. Therefore, it is necessary to study the precipitation behavior of the σ-phase. Fig. 10 presents the change in the
phase and element ratios during the solidification of the melt pools for different samples. The melting point (Tm) of the HEAs decreases
from 1446 C for Mo0 to 1381 C for Mo5 (Fig. 10a). The FCC matrix forms from the liquid phase during solidification, accompanied by
itation in Mo3 begins almost simultaneously with the solidification of the FCC matrix.
Mo1 and Mo5 exhibit a similar trend in terms of the solid-phase content (Figs. 10b and 10c), which is quite different from that of
Mo3 (Lin et al., 2023). In Mo3, the Mo-rich σ phase precipitates first, followed by simultaneous precipitation of the FCC and σ phases.
By contrast, in Mo1 and Mo5, the Mo-rich σ phase precipitates later in the solidification process. As summarized in Fig. 10d, nanosized
σ and µ phases precipitate in the subgrains and at the subgrain boundaries owing to the two-stage solidification (Lin et al., 2023). The
differences in the fractions and distributions of precipitate phases caused by the different Mo contents and the coupling effect with
dislocations lead to different degrees of sharpening of the dislocation cell walls (Fig. 5). It is worth noting that dynamic recrystalli-
zation may occur at the high-temperature tensile conditions of 600 °C (>0.35Tm). However, the Mo-rich precipitates that form during
L-PBF could suppress grain boundary migration via pinning, thereby increasing the size of the recrystallized grains (Wang et al., 2017).

## 3.6. Ab initio calculations and molecular dynamics (MD) simulations for revealing the effects of Mo content and temperature

According to Figs. 2, 6, and 7, there are significant differences in the plasticity of HEAs with varying Mo content. To thoroughly
investigate the reasons behind these differences, we conducted ab initio calculations for auxiliary analysis. As an important
strengthening and hardening mechanism, the morphology and distribution of the deformation twins are closely related to the Mo
=afcc/6[112]Fcc and
p]
=acc/6[211]Fcc. aFcc is the FCC lattice parameter. The stacking sequence of (111)Fcc close-packed planes is ABC|ABC| ABC ..,
bFCC
p2
this resulted in a stacking sequence: ABC|BC|ABC, shown in Fig. 11b. Our ab initio
Burgers vector of the Shockley partial
p1
calculation results, depicted in Fig. 11, reveal that Yisf is approximately 21, −33, and 48 mJ/m2 for HEAs with 0, 6, and 11 at% Mo,
recovery occurs earlier during deformation at 600 C than at 25 C, leading to a rapid decrease in the work-hardening rate at high
strain stages. For Mo5 (11 at%), although it has a lower stacking fault energy, we did not observe a significant amount of twinning in
the matrix. This is because dislocation slip and diffusion mechanisms are more active at high temperatures, which increases the
activation stress for twinning deformation. Additionally, the presence of a large amount of σ-phase attached to the grain boundaries
leads to fracture at lower strain values. This reduction in plastic deformation also decreases the occurrence of twinning to some extent.
The dynamic Hall-Petch effect, induced by the twin boundary in Mo3, introduces new interfaces and reduces the dislocation mean free
path, providing further contribution. Consequently, the dislocation cell patterns of the FeCoCrNiMox HEAs are altered by the
y-axis
a
b
[110] ↑
E011
27A
Tensile stress, GPa
ME011

## 200. Å

Deformation twins occur

## 27. Å

z-axis
0.02

## 72. Å

0.04
0.06

## 64. Å

0.08
[110]
x-axis
0.1
[001]
Tensile strain

valuable insight into the design of FeCoCrNiMox HEAs.
crystal structure with a lattice constant of 3.60 Å. The crystallographic directions along the x, y, and z axes were [001], [110], and
[110], respectively. The nanowire comprised 100,000 atoms, including 23,254, 23,259, 23,255, 23,256, and 6976 Fe, Co, Cr, Ni, and
Mo atoms, respectively, thereby satisfying the atomic ratio of FeCoCrNiMoo.3 (Mo3). Periodic boundary conditions were applied in all
three directions. The top and bottom layers, each measuring 27 Å along the y axis, were fixed. To simulate uniaxial tensile deformation,
these fixed layers were extended in opposite directions along the y axis, with a stretching speed of 0.02 Å/ps. The deformation zone,
subjected to stretching, measured 200 × 72 × 64 Å.
As illustrated in Fig. 12b, Mo3 shows significant stress softening at 600 C compared to that at 25 C. Moreover, the elastic modulus
at 600 C is significantly lower than that at 25 C. As deformation proceeds, twinning occurs, which causes stress drops.
Figs. 13a and 13b illustrate the MD simulations of twin evolution in Mo3 during tensile deformation at room and high tempera-
tures, respectively. The presence of Mo enhances the lattice distortion. During tensile deformation, stacking faults are generated. As the
strain increases, these stacking faults accumulate, leading to the formation of micro twins (Tian et al., 2024). Despite the generation of
micro twins at 25 C, the growth of these micro twins is suppressed as the strain continues to increase, because a significant number of
stacking faults accumulate. This results in an alternating structure of micro twins and stacking faults, thereby enhancing the ductility
(Guo et al., 2024; He et al., 2021b; Jo et al., 2014 ).
As the temperature rises to 600 °C, the SFE gradually increases, as demonstrated by the ab initio calculation results in Fig. 11b. The
local stress of twinning tends to increase with increasing temperature. Thus, the twin lamellae are larger than those at 25 C, as
displayed in Fig. 13b. The stacking faults expand during tensile straining, thereby consuming the twins. Consequently, the strength is
reduced owing to the interaction between stacking faults and twins. Owing to the mutual interaction between the twins and stacking
faults during tensile deformation, Mo3 still has good ductility at 600 C.
Our calculations at the atomic scale indicate that when HEA yields, the ISF structure emerges within the crystal. Some researchers
have characterized through TEM that stacking faults and slip are the initial structures observed during the yielding of FCC alloys. With
increasing temperature, Yisf increases, but studies suggest that Yui exhibits only slight variations. Temperature provides kinetic energy
to atomic motion, leading to lower yield strength of materials at elevated temperatures. Tadmor and Bernstein introduced an alter-
Yisf
γui

## 1.136. - 0.151

(1)
a =
Yui
Yesf
Where the Yui is the maximum value of intrinsic stacking faults, the Yesf is the minimum extrinsic stacking fault. The higher the value
into ESF decreases gradually. ISF without transformation to ESF may generate two neighboring ISFs that can be understood as a twin
simulation. The transformation of ISF into TW requires a significant shear stress to take place, and the magnitude of the shear force,
τTw, can be determined using the following equation (Huang et al., 2006):
Gb1√t
γ
TTW
+
(2)
nb1
n
A stress concentration factor, represented by n, is required in the early stages of nucleation, typically ranging from 2 to 4. The
parameter γ denotes the surface energy of the meta material, whereas b1 refers to the modulus of the Burgers vector of the Shockley
partial dislocation and G represents the shear modulus.
According to the Taylor dislocation hardening model, the local shear stress, tTW, increases with an increase in dislocation density
for FCC metals, which are known for their high-strain hardening ability(Huang et al., 2006).
b
a
0.04
0.06
0.08
0.10
0.04
0.06
0.08
0.10
Tensile strain
FCC
SF
Twin
Tensile strain

τTW = α1Gb√ρ =
∆σ
(3)
M
resulting in twinning in the Mo3 and Mo5 alloys.

## 3.7. Effect of hierarchical microstructure on mechanical properties

The multiscale strengthening mechanisms of the as-built FeCoCrNiMox HEAs are important for clarifying the deformation mech-
anism, particularly the complex mechanical response of the hierarchical microstructure. For metals, the flow stress (oflow) can be
expressed as
+ + + nra
s +
flow =
(4)
+
σth
ath
where σath and σth are thermally independent and dependent stress items, respectively, and σ0 is the friction stress from lattice
resistance (i.e., the PeierlsNabarro stress), which is 125 MPa for Mo0 (Otto et al., 2013) and 237.19 MPa for Mo1 (Dai et al., 2021) at
2MG
2πc
=
exp
(5)
1-v
b(1- ν)
where c is the distance between adjacent slip surfaces (0.206 nm; a/√3), M is the Taylor factor (~3.06 for the FCC matrix), α is a
geometric factor (0.2 for FCC materials), b is the Burgers vector (0.146 nm for Shockley partial dislocations) (Dai et al., 2021), v is
Poisson's ratio, and G is the shear modulus, which is affected by the Mo content (Liu et al., 2020) and temperature (Huang et al., 2015).
Here, G was calculated and measured experimentally using Young's modulus. Note that σo is temperature-sensitive because it depends
largely on the short-range atomic order and strength of the atomic bonds. As the temperature increases, the atomic vibrations increase,
and the atomic bond strength decreases; therefore, σ0 decreases (Wang et al., 2017).
From the ab initio calculations, the SFE of FeCoCrNiMox HEAs decreases with increasing Mo content. Moreover, the stress is below
the twinning threshold at the initial stage of yielding. Therefore, oTw can be temporarily ignored at the yield deformation stage.
The coarse- and fine-grained regions and dislocation cell patterns inside the L-PBF-processed grains regulate dislocation slip during
deformation (Liu et al., 2024). Thus, dislocation strengthening and back-stress strengthening in the initial deformation stage are very
important and collectively increase the hetero-deformation-induced strengthening effect (Chu et al., 2024; Gao et al., 2023; Karthik
and Kim, 2021). For the back stress, which comprises inter- and intragranular stresses, the intergranular stress is nearly zero at the
initial stage of deformation (An et al., 2023), whereas the intragranular stress, caused by the heterogeneously distributed dislocations
piig up at the interac (Gao et al. 022) (. hig-density islocation walls withi the cellular sructure i Mo0), can be rohly
estimated by the dislocation hardening model. For Mo1, Mo3, and Mo5, precipitation and solid-solution strengthening suppress
intragranular stress generation. The empirical relationship for the dislocation hardening stress (op) can be expressed as
= MαGb√ND
(6)
The geometrical factor α is also taken as a constant for FCC martial as 0.2 (Yim et al., 2019). The ρgnDcan be obtained according to
Table 2. Because dislocation and precipitation strengthening are both related to the cellular structure, the root mean square of the two
effects, i.e., cc = √σ2 + ppt2, can be used to evaluate dislocation-cell strengthening in Mo-containing samples (Liu et al., 2023).
For the samples with Mo, the precipitation strengthening stress (oppt) is expressed as
Gb
Dpp
In
e
(7)
=
2π Dppt
b
where Dpt denotes the average particle spacing, calculated using dp
NI0
. Here, dp dpis the average radius of the precipitated
particles and f is the fraction of particles. The characteristics of the precipitates in Mo1, Mo3, and Mo5 were obtained by TEM and in
our previous work (Lin et al., 2024, 2023). Note that σpptσppt is also affected by temperature, similarly to the variation in shear modulus
G.
The atomic numbers of Co, Cr, Fe, and Ni are sequentially adjacent; therefore, there is little difference in their atomic radii.
Consequently, the atomic size mismatch within FCC FeCoCrNi HEAs is negligible. Hence, only Mo is recognized as a strengthening
element. The solid-solution strengthening stress (oss) caused by Mo is expressed as
= =
(8)

2002).
From the HallPetch relation, the grain boundary strengthening stress (σGB) is given as
kHP
=
(9)
√dσGB
\svr
stitutional elements. This leads to a correction term of 48[Mo] (where [Mo] is the Mo concentration in at%) (Kenji et al., 2002) for kHP
in the Fe-CrNi system, which is quite near the measured kHp value of 297 MPa/μm1/2
for Mo1 (Dai et al., 2021). Therefore, σGB is
modified as follows:
(kHP + 48Mo)
(10)
B =
√dσGB
\svqrt
Figs. 14a and 14b compare the sum and contribution of each stress strengthening term to the yield strength during tensile
deformation at room and high temperatures, respectively, which show good agreement with the experimental results. The most
significant contribution is dislocation cell-coupled strengthening, which is characteristic of L-PBF-processed metals. Compared with
Mo0, an appropriate Mo addition (≥7 at%) can markedly enhance the yield strength of FeCoCrNi-based HEAs, especially at high
temperatures. This is because, although high temperatures can induce grain recovery, the solid-solution and precipitation strength-
ening induced by Mo can impede dislocation slip and exert a grain-boundary pinning effect.
However, the TEM characterization, ab initio calculations, and MD simulations reveal that excess Mo (e.g., 11.11 at%, Mo5) leads to
excessive precipitation at grain boundaries. This significantly increases the SFE at high temperatures and hinders continuous dislo-
cation slip after the initiation of yielding, culminating in a substantial decrease in the uniform elongation of samples with high Mo
contents. Although the SFE of samples with low or no Mo (~2.4 at%, Mo1; 0 at%, Mo0) increases less than that of Mo5 at high
temperatures, the fracture of these samples occurs before the tensile stress reaches the critical value for twinning, resulting in a sig-
nificant loss of strength and toughness and compromising their high-temperature performance. Moreover, the critical twinning stress
decreases within coarse grains (Cai et al., 2017; Wagner and Laplanche, 2023); therefore, the larger grain size of Mo3 is conducive to
twinning. The dynamic HallPetch effect further enhances the strain-hardening ability (Liu et al., 2022). Consequently, an optimal Mo
content (~7 at%, Mo3) can maintain the effects of solid-solution and precipitation strengthening while also inducing twinning in the
later stages of deformation, which further enhances the dislocation hardening ability.
Fig. 14c depicts the distinctive mechanical performance of the L-PBF-processed FeCoCrNiMox HEAs versus other alloys at 600 C
(see Fig. 2d and the Supplementary Material for further detail). By incorporating an optimal amount of Mo (711 at%), it is possible to
regulate multiple strengthening and hardening mechanisms. These mechanisms include solid-solution strengthening, grain-boundary
strengthening, precipitation strengthening, and twinning. This regulation facilitates enhanced strengthductility synergy in Mo3 at
elevated temperatures.

## 4. Conclusions

In this study, we systematically studied the mechanical properties of L-PBF additively manufactured FeCoCrNiMox HEAs with
varying Mo contents at both room and elevated temperatures (25 and 600 °C, respectively). A multiscale analysis, incorporating SEM,
EBSD, TEM, and quantitative simulations, was conducted to assess the microstructural evolution and tensile deformation and elucidate
the underlying mechanisms. The conclusions drawn from this study are as follows:

## 1. The L-PBF-processed FeCoCrNiMox specimens exhibit a near-defect-free matrix with distinct dislocation cell patterns. With the

addition of Mo (2.44, 6.98, and 11.11 at%), σ-phase precipitation increases, accompanied by sharpening of the dislocation cell
walls.

## 2. In conjunction with ab initio calculations, MD simulations, and TEM observations, the SFE of the FeCoCrNiMox HEAs decreases with

increasing Mo content and increases at elevated temperatures. As a result, twinning is more likely to occur at room temperature for
all samples. However, at 600 °C, twinning is only observed for Mo3 owing to the increased SFE.

## 3. The addition of Mo to the FeCoCrNi matrix promotes both solid-solution and precipitation strengthening. By leveraging the

versatility and rapid cooling of L-PBF, the introduction of an appropriate amount of Mo (711 at%) allows for precise micro-
structural control. This results in the simultaneous or sequential regulation of multiple strengthening mechanisms, including
dislocation hardening, solid-solution strengthening, precipitation strengthening, hetero-deformation-induced strengthening, and
twinning. Consequently, FeCoCrNiMox HEAs (x = 0.30.5) exhibit improved formability at room temperature and enhanced
strengthductility synergy at high temperatures. Specifically, the YS, UTS, and uniform elongation reach 580 MPa, 800 MPa, and
20%, respectively.

a
b 1200
Friction
Hall-Petch
Hall-Petch
Yield strength, MPa
Dislocation cell coupled
MPa
Dislocation cell coupled
Solid solution
Solid solution
Exp. 25°
Yield strength, I
Exp. 600°C
Mo0
Mo3
Mo5
Mo1
Mo0
Mo1
Mo3
Mo5
600°
c
Mo5
Mo3
Strength, MPa
Dislocation cell pattern
Nano σ/μ-phase ppts
Mo-solid solution
Nano twins (Mo3)
Mo1
Strength-ductility
trade off
Mo0
Ductility
Fig. 14. Comparison of yield strength as a cumulative structural calculation of various stress hardening terms with experimental results: (a) 25 C,
(b) 600 C. (c) Schematic of the deformation mechanisms of L-PBFed Mo3 HEAs achieving enhanced strength-ductility synergy at elevated
temperature.
on key microstructural characteristics such as stacking faults, twins, precipitates, and dislocation cell patterns, verifying the feasibility
of using L-PBF to regulate the sequential activation of different strengthening mechanisms. Conventional methods such as SEM, TEM,
and EBSD cannot capture the microstructure and twinning process at high temperatures. However, we have revealed this process
through first-principles calculations and molecular dynamics simulations. By combining experimental observations with simulations,
we have thoroughly analyzed the plastic deformation mechanisms of HEA alloys. This approach provides valuable insights for the
development of new materials. This study provides valuable insights for structural HEAs to achieve synergistic high-temperature
mechanical properties, thereby proving their significance and practicality in both scientific and engineering contexts.

## CRediT Authorship

Danyang Lin: Writing original draft, Investigation, Funding acquisition, Conceptualization. Jixu Hu: Project administration,
Methodology, Investigation, Conceptualization. Renhao Wu: Writing - review & editing, Visualization, Investigation, Funding
acquisition. Yazhou Liu: Visualization, Investigation. Xiaoqing Li: Visualization, Investigation. Man Jae SaGong: Validation,

## Declaration of Interest

The authors declare that they have no known competing financial interests or personal relationships that could have appeared to
influence the work reported in this paper.

## Data Availability

Data will be made available on request.

## Acknowledgements

The authors are greatly appreciated for the financial support by the National Research Foundation of Korea (NRF) grant funded by
the Korea government (MSIP) (Nos. NRF-2021R1A2C3006662 and NRF-2022R1A5A1030054). Dr. Renhao Wu is supported by Brain
Pool Program through the NRF of Korea, funded by the Ministry of Science and ICT (NRF-RS202300263999). Dr. X. Li gratefully
acknowledges financial support from the Swedish Research Council, the Göran Gustafsson Foundation, and the Carl Tryggers Foun-
dation. The computations were enabled by resources provided by the National Academic Infrastructure for Supercomputing in Sweden
(NAISS) at Linköping partially funded by the Swedish Research Council through grant agreement no.202206725. This work is also
supported by the National Natural Science Foundation of China (Grant No. 52175307 by Dr. Song, and No. 52205348 by Dr. Lin), and
the Natural Science Foundation of Shandong Province (Grant: ZR2023JQ021 by Dr. Song and ZR2022QE087 by Dr. Lin).

## Supplementary Material

## Supplementary Material