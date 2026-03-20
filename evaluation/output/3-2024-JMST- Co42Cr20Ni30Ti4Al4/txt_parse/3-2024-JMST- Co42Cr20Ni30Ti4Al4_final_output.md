JMST
Journal of Materials Science & Technology
Research Article
An additively manufactured precipitation hardening medium entropy
alloy with excellent strength-ductility synergy over a wide
temperature range
Jing Huang a,b, Wanpeng Li b,c,*, Tao Yangb, Tzu-Hsiu Choub, Rui Zhoub, Bin Liu a,
Jacob C. Huangb,d,*, Yong Liu a,*
a State Key Laboratory of Powder Metallurgy, Central South University, Changsha 410083, China
b Department of Materials Science and Engineering, City University of Hong Kong, Kowloon 99077, Hong Kong SAR, China
c TRACE EM Unit, City University of Hong Kong, Kowloon 999077, Hong Kong SAR, China
d Department of Materials and Optoelectronic Science, National Sun Yat-Sen University, Kaohsiung 804, Taiwan, China

## ARTICLE INFO

## ABSTRACT

Article history:
Revised 12 January 2024
C042Cr20Niz0Ti4Al4 quinary MEA which exhibits a superiority of mechanical properties over a wide tem-
perature ranging from 77 to 873 K via selective laser melting (SLM) and post-heat treatment. The present

## Keywords

Additive manufacturing

## 22.7. % at 298 K, a UTS of 1944 MPa with a TE of 22.6 % at 77 K, and a UTS of 1147 MPa with a TE of

Selective laser melting

## 9.1. % at 873 K. The excellent mechanical properties stem from the microstructures composed of partially

Medium entropy alloy
refined grains and heterogeneously precipitated L12 phase due to the concurrence of recrystallization
Multi-principal-element alloy
and precipitation. The grain boundary hardening, precipitation hardening, and dislocation hardening con-
Precipitation hardening
tribute to the high YS at 298 and 77 K. Interactions of nano-spaced stacking faults (SFs) including SFs
Mechanical properties
networks, Lomer-Cottrell locks (L-C locks), and anti-phase boundaries (APBs) induced by the shearing of
L12 phase are responsible for the high strain hardening rate and plasticity at 77 K. Our work provides
a new insight for the incorporation of precipitation hardening and additive manufacturing technology,
paving the avenue for the development of high-performance structural materials.
© 2024 Published by Elsevier Ltd on behalf of The editorial office of Journal of Materials Science &
Technology.

## 1. Introduction

among which the L12 phase strengthened MPEAs exhibit superior
mechanical properties [3-9]. The coherent interface between the
High-performance alloys with gigapascal strength and good
L12 phase and the FCC matrix could effectively reduce the stress
ductility are highly desired for modern engineering applications.
concentration and avoid the premature failure of the alloy [10-
The idea of high entropy alloy (HEA), medium entropy alloy (MEA),
12]. The L12 precipitates introduced via the co-doping of Ti and Al
and multi-principal element alloy (MPEA) provides a new avenue
exhibit lower environmental embrittlement, which achieves a less
for the further extension of the up-limit of strength-ductility com-
loss of ductility in the intermetallic phase strengthened alloys [4].
bination in the face-centered cubic (FCC) metal materials [1,2]. The
Moreover, the small interfacial energy of the L12/FCC interface and
high work-hardening capability but relatively low strength of the
the slower diffusion effect of HEA contribute to the thermal sta-
face-centered-cubic (FCC) MPEAs [2], which are mainly composed
bility of the L12 phase [13], and the L12 solvus temperature can
of Fe, Co, Cr, Ni, and Mn, makes it a quite hot topic to strengthen
be raised to 1150 °C with appropriate alloying optimization [14],
them. As an effective and widely used strengthening method, pre-
making the L12 phase a promising strengthening phase at elevated
cipitation hardening has also been adopted into the FCC MPEAs,
temperatures.
The equiatomic CoCrNi system exhibits excellent work-
hardening ability, and a more prominent combination of strength
*
Corresponding authors.
and ductility compared with other CoCrFeMnNi HEAs at room
E-mail
addresses:
wanpengli2-c@my.cityu.edu.hk
(W.
Li),
temperature and especially the cryogenic temperature [2,15],
jacobc@faculty.nsysu.edu.tw (J.C. Huang), yonliu@csu.edu.cn (Y. Liu).
https://doi.org/10.1016/j.jmst.2024.02.077

J. Huang, W. Li, T. Yang et al.
Journal of Materials Science & Technology 197 (2024) 247264
making the CoCrNi MEA an ideal FCC matrix for the precipitation
microstructure composed of precipitation and heterogeneous grain
strengthening. The exceptional mechanical properties of CoCrNi
structure, and the inherent high density of dislocations, exhibit-
ing superior mechanical properties at cryogenic and ambient tem-
perature. The SLMed (FeCoNi)86Ti7Al7 alloy reported by Mu et al.
mitted be closely related ostacking fault energy ].
[31] exhibits a unique dislocation-precipitate skeleton (DPS), ultra-
high ultimate tensile strength of ~1.8 GPa, and maximum elonga-
reveal that tuning the content of Co can regulate the SE of
tion of ~16 % at the ambient temperature. However, it meets a bot-
the alloy and achieve higher work-hardening ability, making the
tleneck to raise the volume fraction of L12 precipitates with the
further optimization of mechanical properties of CoCrNi MEAs a
equiatomic CoCrNi matrix, since higher Ti/Al contents bring about
promising project [16,17]. For Ti/Al containing CoCrNi-based MEAs,
the precipitation of o phase that deteriorates mechanical proper-
a lower content of Cr is also reported to be effective in reducing
ties [32-34]. The equiatomic FeCoNi matrix shows a large solid
the formation of the detrimental o phase, indicating the compo-
solubility of Al and Ti, but the inevitable L21 phase (Ni2TiAl) is
sition design is of substantial importance in the optimization of
harmful to the mechanical performance at elevated temperatures
precipitation-strengthened CoCrNi-based MEAs [6].
[31,35,36]. Hence, increasing the volume fraction of L12 precipi-
However, the fabrication of casting alloys mentioned above
tates and avoiding the formation of detrimental phases are striv-
mostly involves multiple passes of mechanical treatments and heat
ing goals for the alloy design of L12-strengthened AMed MPEAs.
treatments to attain a tailored microstructure, making the produc-
Meanwhile, modern engineering has put forward more urgent re-
tion routes laborious work, especially for the complex geometries.
quests for structural materials with excellent mechanical proper-
Compared with the conventional fabrication routes, additive man-
ties at harsh working conditions [21], such as at cryogenic or ele-
ufacturing (AM) exhibits several superiorities, such as a high de-
vated temperatures, making the development of high-performance
gree of geometrical freedom in the design and production of metal
AMed alloys a challenging but promising subject.
In this study, a non-equiatomic C042Cr20Ni30Ti4Al4 quinary MEA
components with complex structures, a substantial reduction in
the loss of raw materials during post-processing compared to the
was developed via SLM plus the post-heat treatment, exhibiting
conventional fabrication method, and the consequent time, energy,
superior mechanical properties over a wide temperature range
and cost-saving [1821]. Moreover, the high energy input and high
(from 77 to 873 K). A high volume fraction of heterogeneously pre-
cooling rate of AM methods can suppress phase transition and in-
cipitated L12 precipitates and the partially recrystallized FCC ma-
termetallic formation, and also lead to a fine microstructure, mak-
trix were introduced into the MEA simultaneously without other
ing it a potential fabrication route for MPEAs.
harmful phases. The strengthening and deformation mechanisms
As one of the most prominent AM techniques, selective laser
were investigated and discussed based on the microstructural ob-
melting (SLM) is widely applied to research about HEAs. The
servation. Our work provides insights into the development of
research about the selective laser melted (SLMed) equiatomic
AMed L12 strengthened alloys, and also indicates that, with the
FeCoCrNiMn-based HEAs indicated that the fine grain structures,
combination of proper elemental designs and heat treatments, ad-
cellular structures, and dislocations brought by SLM methods do
ditive manufacturing could be a promising processing technique
favor the improvement on the strength of HEAs compared to the
for high-performance structural materials.
counterparts produced by casting [2224]. The high cooling rate of
SLM also facilitates the formation of the single FCC structure and

## 2. Materials and methods

the introduction of solid solution hardening brought by the sub-
stitutional and interstitial solute atoms. Park et al. [25] reported

## 2.1. Alloy design

a simultaneous improvement in the strength and ductility of Fe-
CoCrNiMn SLMed HEA by introducing 1 % C. Fujieda et al. [26] at-
The nominal composition of the alloy and heat treatment pro-
tributed the decent synergy of strength-ductility (tensile strength
cesses were designed according to previous studies and experi-
of 1178.0 MPa and elongation of 25.8 %) and the improved cor-
ments. Firstly, higher contents of Ni (30 at.%), Ti (4 at.%), and Al
rosion resistance of the Co1.5CrFeNi.5Ti0.5Mo0.1 alloy to fine grain
(4 at.%) were chosen for introducing a high volume fraction of
structures and the absence of NiTi intermetallic compounds. In
the L12 phase with high anti-phase boundary (APB) energy [37].
addition to the solid solution hardening effect, introducing inter-
Although even higher contents of Ti and Al were verified to be
stitial atoms, such as nitrogen, can lead to further strain hardening
practical and effective in strengthening the alloy, it is possible to
mechanisms in SLMed HEAs. Song et al. [27] reported that the ni-
bring about the B2 phase and L21 phase [35,38]. Relatively lower
trogen doping induced a local grain refinement in the re-melted
Cr was preferred to avoid the introduction of the σ phase [33,34].
regions during SLM, and the subsequent heterogeneous deforma-
High content of Co was preferred to lower the SFE, which may en-
tion induced hardening. For the eutectic HEA, the lamellar eutec-
dow the alloy with better sustainability of a high strain-hardening
tic structure can be refined via the application of SLM. Yang et al.
rate at higher strain conditions [39,40]. The pseudo-binary equi-
[28] reported a SLMed Ni30C030Cr10Fe10Al18W1Mo1 (at.%) with an
librium phase diagram with varying Cr content was calculated by
ultra-fine lamellar spacing of 150-200 nm within the small colony
the Thermo-Calc software (TCHEA5 database), as shown in Fig. S1
with the size of 2-6 µm, exhibiting a yield strength of 1.0 Gpa,
in Supplementary Information. Fig. S1 indicates that 42 at.% of Co
ultimate tensile strength of 1.4 GPa, and uniform elongation larger
and 20 at.% of Cr can effectively avoid the possible detrimental σ
than 18 %. Introducing nano secondary particles is also feasible in
phase. Therefore, the composition of the alloy was determined to
SLMed HEAs. Lu et al. [29] produced a FeCoCrNiMn-TiC HEA com-
be C042Cr20Ni30Ti4Al4 (at.%).
posite via SLM, which exhibits both an increase in strength and
The configuration entropy of the C042Cr20Ni30Ti4Al4 (at.%) al-
ductility compared to the FeCoCrNiMn HEA.
loy was calculated to be 1.3R (The calculation method is shown in
Moreover, with a tailored composition and post-heat treat-
Section 2 in Supplementary Information). It meets the definition
ments, nano precipitates, such as the L12 phase mentioned above,
of MEAs [41]: 1.0R ≤ ΔSconf ≤ 1.5R, when the alloy is in a random
can also be introduced into the SLMed HEAs, leading to a further
solution state. Therefore, the C042Cr20Ni30Ti4Al4 (at.%) alloy is re-
improvement in the mechanical properties with the combination
ferred to as an MEA.
of precipitation hardening and advantages of the SLM method. The
The suitable parameters for the heat treatments were chosen
(CoCrNi)94TiAl3 alloy reported by Yao et al. [30] benefits from
via the combination of annealing trials, hardness tests, and mi-
the low stacking faults energy (SFE) of the matrix, the hierarchical
crostructural characterizations. All the trials were attempted in

joarmdt of maeorn
(a)
Intensity (a.u.)
(b)
FCC
Accumulative ratio (%)
Distribution ratio
average
= 22.9

## 20. (deg)

## 10. μm

Diameter (μm)
(c)
(d)
FCC
Intensity (a.a.)
L12
Intensity (a.u.)

## 22. 24 26 28 30 32 34 36

## 28. (deg)

JNNNE
As-annealed
x
Z: Building Direction
As-built
X: Tensile Direction
Y: Transverse Direction

## 20. (deg)

Fig. 1. (a) The morphology of the pre-alloyed powder. (b) The particle size distribution map of the pre-alloyed powder. (c) Schematic drawing of the SLM process. And (d)
the XRD patterns of the as-built and as-annealed alloys.
SLMed samples. The results indicated that annealing at 973 K for
heat treatment are referred to as the as-built alloy, and the blocks
that went through two passes of heat treatments are referred to as

## 64. h was the optimum heat treatment condition.

the as-annealed alloy.

## 2.2. Materials fabrication

## 2.3. Mechanical testing

Pre-alloyed C042Cr2oNi30Ti4Al4 (at.%) powders were produced
The specimens for tensile tests were prepared via slicing the
by gas atomization, exhibiting spherical shape and FcC structure
as-built blocks by wire-electrode cutting. The uniaxial tensile tests
as shown in Fig. 1(a). The particle size ranged from 8 to 60 µm
at room temperature (298 K) were conducted on the Instron 3369
with an average diameter of 22.9 µm (Fig. 1(b)). The SLM pro-
machine equipped with an extensometer, using flat dog-bone-
cess was conducted on a sandblasted stainless-steel substrate using
shaped specimens with a gage length of 20 mm, and width of
a commercial machine (FS121M-B5, Farsoon, China), with a laser

## 4. mm. The uniaxial tensile tests at 77 K were conducted on an

power of 200 W, scanning speed of 1000 mm s-1, hatching space
MTS Alliance RT 30 tensile machine, using flat dog-bone-shaped
of 90 µm, beam size of 40 µm and the layer thickness of 40 µm.
specimens with a gage length of 12.5 mm, and width of 3 mm. The
Argon atmosphere was used to prevent oxidation during SLM. The
uniaxial tensile tests at 773 and 873 K were conducted on an RRC-
laser was rotated 67° in each scanning layer as shown in Fig. 1(c).

## 50. testing machine, using flat dog-bone-shaped specimens with a

The geometry of the as-built material block was in a cuboid shape,
gage length of 8 mm, and a width of 3.4 mm. Each sample has
with a length of 65 mm, width of 18 mm, and height of 10 mm.
a thickness of ~1.5 mm after polishing. A strain rate of 1 x 10-3
The as-built material blocks together with the substrate were an-
was applied to all the tensile tests. Each test condition was re-
nealed at 723 K for 3 h followed by water quenching to release the
peated at least three times to ensure the reproducibility. In partic-
residual stress. After the residual stress relief heat treatment, the
ular, before starting a tensile test at 77 K, the specimen was held
as-built blocks were removed from the substrate by wire-electrode
at 77 K for 5 min. Before starting a tensile test at 773 and 873 K,
cutting, then annealed at 973 K for 64 h followed by water quench-
the specimen was held at the testing temperature for 10 min.
ing. The as-built blocks that went through the residual stress relief

J. Huang, W. Li, T. Yang et al.
Journal of Materials Science & Technology 197 (2024) 247264

## 2.4. Microstructural characterization

the decreasing values of Kernel average misorientation (KAM). The
corresponding KAM distribution maps and grain size distribution
The particle size distribution of the pre-alloyed powders was
maps are shown in Fig. S3.
estimated by using a laser diffraction particle size analyzer
Fig. 3 illustrates the detailed microstructures of the alloy be-
(Malvern, Micro-plus). The porosity of the as-built alloy was mea-
fore and after the annealing treatment. As shown in Fig. 3(a), the
sured by the metallographic methods. The densities of the as-built
grains in the as-built alloy are composed of uniform sub-grain cel-
alloy and the casting alloy with the same composition were mea-
lular structures, and no precipitates occur. The cellular structures
sured by the Archimedes method. Each density data was mea-
are columnar structures that are displayed cross-sectionally.
sured three times to ensure accuracy. The crystal structure and
After the annealing, the cellular structures become coarsened.
phase composition of pre-alloyed powders, the as-built alloy, and
The average diameter of cellular structures in the as-built alloy
the as-annealed alloy were characterized by X-ray diffraction (XRD,
and the as-annealed alloy is measured to be 0.63 and 1.24 µm,
Rigaku D/MAx-2250, Japan) with Cu Kα radiation. The bulk sam-
respectively. The non-uniform growth of discontinuous precipita-
ples for XRD characterization were polished using standard me-
tion (DP) colonies is prevalently around grain boundaries, which
chanical polishing procedures. The scanning step for all the XRD
is indicated by arrows in Fig. 3(b). Discontinuous precipitates ex-
measurements is 0.02°. The scanning in the 2θ range of 20°-100°
hibit typical lamellar or short-rod shape. At higher magnifica-
was conducted with a scanning speed of 5° min-1. A slow scan
tion, it can be observed that the DP not only happens at re-
in the 2θ range of 20°37° was conducted with a scanning speed
gions near grain boundaries but can also proceed deeply into the
of 0.5° min-1. The micromorphology of pre-alloyed powders, the
grains as presented in Fig. 3(c). Discontinuous precipitates dis-
overview of the microstructures, and fracture surfaces were con-
tributed more inside the grain exhibit finer and shorter rod shapes,
ducted on the scanning electron microscopy (SEM, TESCAN MIRA4
some even near-spherical. Moreover, DP is also evidently observed
LMH) equipped with an energy dispersive spectrometer (EDS, Ul-
in the newly formed fine recrystallized grains where the cellu-
tim Max 40) and electron backscatter diffraction (EBSD) detector.
lar structures vanish (Fig. 3(d)) and some annealing twins form
The specimen sheets for SEM and EBSD analysis were firstly me-
(Fig. 3(e)). However, no visible precipitate is observed in the re-
chanically ground to 3000-grit SiC paper, followed by mechanical
gions typically shown in Fig. 3(f) where cellular structures are
polishing by colloidal silica suspension, and finally electrochemi-
undamaged.
cally polished by 10 % HCl04 + 90 % C2H5OH solution at 233 K
To further investigate the microstructures, TEM characterization
and 25 V. The EBSD data were analyzed by the Aztec Crystal
was conducted. Fig. 4(a) shows the distinct cellular structures with
software. TEM characterizations were performed by transmission
sizes around 0.5-1 µm in the as-built alloy. The inserted selected-
electron microscope (TEM, JEOL JEM-2100F, and JEM-ARM300F2,
area electron diffraction (SAED) pattern indicates that the as-built
Japan) equipped with an energy dispersive spectrometer (EDS).
alloy has a single FCC structure. The two-beam bright-field (BF)
STEM (scanning transmission electron microscopy) images were
image (Fig. 4(b)) and low-angle annular dark-field (LAADF) scan-
taken using an annular-type detector with a collection angle rang-
ning transmission microscopy (STEM) image (Fig. 4(c)) reveal that
ing from 92 to 228 mrad. The corresponding EDS mapping was
the cellular boundaries are composed of dislocation walls. In ad-
collected and processed by the auto filter in the Oxford INCA soft-
dition to the dislocation walls, there are also many dislocations
ware. TEM samples were sliced by wire-electrode cutting, and then
inside the cellular structures. The corresponding STEM energy-
mechanically ground to about 50 µm by SiC paper, and finally
dispersive X-ray spectroscopy (EDS) results show the Ti segregation
twin-jet electro-polished in 10 % HCl04 + 90 % C2H5OH solution
on the cellular boundaries.
The TEM BF image (Fig. 5(a)) and the corresponding dark-field
at 243 K and 25 V.
(DF) image (Fig. 5(b)) distinctly show the strip-like morphology
of discontinuous precipitates. The inserted SAED pattern confirms

## 3. Results

that the matrix has FCC structure and the discontinuous precip-
itates have the L12 structure. The two-beam BF image (Fig. 5(c))

## 3.1. As-built and as-annealed microstructures

shows a relatively larger view of the DP region. The tangled dis-
locations that make up the cell boundaries are mostly annihilated,
The porosity value of the as-built alloy was measured to be
and only some traces of remaining dislocations walls can still be

## 0.048. % via metallographic methods. The porosity value is the av-

identified as referred to by arrows in Fig. 5(c). The high-angle an-
erage value of the area ratios of porosities in the metallographs
nular dark-field (HAADF) image (Fig. 5(d)) also shows that the orig-
shown in Fig. S2. The areas were measured by Image J. The den-
inal cellular boundaries composed of tangled dislocations are elim-
sity of the as-built alloy is 8.07 ± 0.02 g mm-3, and the density
inated, but the distribution of precipitates in the DP region exhibits
of the corresponding casting alloy is 8.13 ± 0.02 g mm-3. There-
a cellular contour. The corresponding STEM-EDS results (Fig. 5(e))
fore, the relative density is calculated to be 99.26 %, indicating
show obvious segregation of Ni, Ti, and Al along cellular contours.
that the as-built alloy is nearly fully dense. The XRD patterns in
Fig. 6 gives the HAADF-STEM image and the corresponding EDS
Fig. 1(d) indicate that the FCC phase is present in the as-built and
mapping of discontinuous L12 precipitates with higher magnifica-
as-annealed alloys, while the L12 precipitate phase is introduced
tion. The concentration of Ni, Ti, and Al inside the cellular con-
during the annealing process. Fig. 2 shows the comparison of the
tour exhibits a stripe-like shape, which corresponds to the mor-
grain structures before and after the annealing. The as-built alloy
phology of discontinuous L12 precipitates. Meanwhile, the HAADF-
exhibits clear melting tracks (Fig. 2(a)) and typical columnar grains
STEM image shows that there are more L12 precipitates along the
(Fig. 2(b)). After annealing, a large number of fine grains emerge
cellular contour, indicating that more L12 precipitates form along
as shown in Fig. 2(c, d), indicating that recrystallization happens.
the original cellular boundaries where there was a segregation of
Given the morphology of grains in the as-annealed alloy, the re-
Ti, and they subsequently make up of the cellular contour with no
crystallization has only partially proceeded [42,43]. The decreasing
dislocations. But in the areas near grain boundaries, where discon-
grain reference orientation deviation (GROD) in the as-annealed al-
tinuous precipitates show larger sizes, cellular contours with en-
loy, which is shown by the comparison between Fig. 2(e, f) and
richment of Ni, Ti, and Al are eliminated as shown in Fig. S4.
Fig. 2(g, h), confirms the occurrence of recrystallization. Corre-
In addition to the DP region with annihilated dislocation walls,
spondingly, the newly formed fine recrystallized grains lead to a
the undamaged cellular structures can be observed in the as-
decreasing average grain size and a decrease in the density of
annealed alloy as Fig. 7(a) shows. The inserted SAED pattern
geometrically necessary dislocations (GNDs) which is reflected by

joarmdt of maeor
−(
(a)
(c)

## 100. μm

(b)
(p)
(h)

## 100. μm

0°
Grain Boundaries
2°-10°
> 10°
plane (d, h) for the as-annealed alloy, respectively.
a)
(c)
N

## 5. μm

um
(d)
e)
(f)

## 2. μm

um
structures. ) The as-annealed alloy showing D around grain boundaries. c) An enlarged view of the inside region of the grains in the as-annealed alloy showing ne
isiuu prepitates. he newly or recytalliz gra he snalealloy. he aling tw hsneale ly. Regns w
undamaged cellular structures but no visible precipitates in the as-annealed alloy.
(Fig. 7(a)) and the DF image (Fig. 7(b)), which corresponds to the
(Fig. 7(d)) also shows an obvious enrichment of Ni, Ti, and Al along
area labelled with the red dash-lined rectangle in Fig. 7(a), in-
cell boundaries. The LAADF-STEM image with higher magnification
dicate the continuous precipitation (CP) of L12 precipitates. The
of the region inside the cellular structure, where marked with a
continuous L12 precipitates are spherical, and much smaller than
dash-lined square in Fig. 7(c), and its corresponding STEM-EDS re-
the discontinuous L12 precipitates so they can only be character-
sults (Fig. 7(e)) confirm the presence of continuous L12 precipi-
ized via TEM. Hence, there is no visible precipitate in Fig. 3(f).
tates inside the cellular structure. The enlarged view of the disloca-
The LAADF-STEM image of the CP region (Fig. 7(c)) shows that
tion wall, where marked with a dash-lined circle in Fig. 7(c), and
cellular boundaries composed of dislocation walls are still main-
the corresponding STEM-EDS results (Fig. 7(f)) confirm that there
tained after the CP happens. The corresponding STEM-EDS results
are also L12 precipitates within the dislocation wall. Compared

(b)
FCC
Z=.[101]
J

## 0.5. μm

g.111
Co
Ni
Fig. 4. TEM observations of the as-built alloy. (a) TEM BF image of the as-built microstructure showing cellular structures. (b) TEM two-beam BF image showing cell
boundaries composed of dislocations. (c) LAADF-STEM image and the corresponding STEM-EDS maps of cellular structures in the as-built alloy.
Table 1
with the intra-cellular precipitates, the inter-cellular precipitates
Mechanical properties of the as-built alloy and as-annealed alloy.
exhibit a more ellipsoidal shape. Similar dislocation-precipitation
skeletons were also observed in the AMed Fe28C029.5Ni27.5Ti8.5Al6.5
Test
Alloys
temperatures (K)
YS (MPa)
UTS (MPa)
TE (%)
alloy [31], and the morphology difference between intra-cellular
precipitates and the inter-cellular precipitates was ascribed to the
As-built

## 953. ± 4

## 1370. ± 14

## 49.9. ± 2.5

pipe-diffusion mechanism and the elemental dragging effect. The

## 734. ± 9

## 995. ± 7

## 37.7. ± 1.0

atomic-scale high-resolution (HR) TEM observation in Fig. 8 shows
As-annealed

## 1341. ± 17

## 1944. ± 6

## 22.6. ± 2.9

## 1180. ± 10

## 1586. ± 11

## 22.7. ± 0.3

that both the discontinuous precipitates and continuous precipi-

## 977. ± 3

## 1263. ± 10

## 13.8. ± 1.4

tates are fully coherent with the FCC matrix. The corresponding

## 926. ± 11

## 1147. ± 16

## 9.1. ± 0.6

fast Fourier transform (FFT) patterns further confirm the L12 struc-
ture of precipitates.

## 3.2. Mechanical properties at different temperatures

tures, the as-annealed alloy maintains high UTS of 1263 ± 10 and

## 1147. ± 16 MPa at 773 and 873 K, with decent ductility of 13.8 % ±

The representative engineering stress-strain curves of the as-

## 1.4. % and 9.1 % ± 0.6 %, respectively.

built alloy tested at 298 and 77 K, and the as-annealed alloy at
The true stress-true strain curves and the corresponding strain-
298, 77, 773, and 873 K are presented in Fig. 9(a). The values of
hardening rate curves of the as-built alloys and as-annealed al-
yield strength (YS), ultimate tensile strength (UTS), and total elon-
loys tested at different temperatures are shown in Fig. 9(b). For
gation (TE) are listed in Table 1. Compared to the results at 298 K,
the same alloy, the strain-hardening rate at 77 K is the highest,
the as-built alloy shows an increase in both strength and ductility
showing an apparent temperature dependence. Meanwhile, com-
at 77 K.
pared to the as-built alloy, the as-annealed alloy shows a distinctly
After annealing, the alloy at 298 K exhibits a great improve-
higher strain-hardening rate at the same temperature. Fig. 9(c-f)
ment for the YS (734 ± 9 to 1180 ± 10 MPa) and UTS (995 ± 7
presents the comparisons of mechanical properties between the
as-annealed alloy and some other AMed alloys, including MPEAs
to 1586 ± 11 MPa) and still maintains excellent ductility (22.7 %
[2224,30,31,35], MPEA/TiC composite materials [29], eutectic al-
± 0.3 %). When the testing temperature decreases to 77 K, the
loys [28], Inconel 718 alloy [4447], Alloy 625 [48], 316 L steel
YS and UTS increase to 1341 ± 17 and 1944 ± 6 MPa, respec-
[4951], and AISI 4140 steel [52]. As shown in Fig. 9(c), although
tively. Meanwhile, the ductility is unaffected. At elevated tempera-

(a)
FCC
(b)
(d)
Z=[001] ©L12
nm
pmill
C
g=002

## 0.5. μm

(e)
Co
Cr
Ni
Ti
μm
enrichment of Ni, Ti, and Al along the cellular contour.
AI
Fig. 6. HAADF-STEM image and the corresponding STEM-EDS mapping of the DP region with higher magnification.
the total elongation of the as-annealed alloy is comparable with
hibits the highest strengths. For the mechanical properties at ele-
other alloys, the ultimate tensile strength is prominently higher
vated temperatures shown in Fig. 9(e, f), the as-annealed alloy ex-
at 77 K. The comparison of yield strengths and total elongations
hibits higher strength. In general, the as-annealed alloy presented
shows a similar trend in Fig. S5(a). For mechanical properties at
in our current work exhibits excellent mechanical properties over

## 298. K shown in Figs. 9(d) and S5(b), the as-annealed alloy exhibits

a wide range of temperatures from 77 to 873 K, especially the
a better strength-ductility combination than the alloy which ex-
prominent mechanical properties at 77 K.

(a)
(c)
-
Co
nm
O
FCC
Z=[001]
L12
(b)
Co

## 0.5. μm

(d)
Co
Ni
Ti

## 0.5. μm

L12 precipitates. (c) LAADF-STEM image of the CP region showing the intact cellular boundaries composed of dislocations. (d) STEM-EDS corresponding to (c) showing the
STEM-EDS results of the inter-cellular region, indicated by the circle in (c).
a
nm
FCC
L12
Fig. 8. (a) HR-TEM image of the discontinuous precipitate with the FFT patterns corresponding to regions labelled with numbers 1 and 2. (b) HR-TEM image of the continuous
precipitate with the FT patterns corresponding to regions labelled with numbers 3 and 4.

## 3.3. Deformation substructures

during the plastic deformation. The thickened cell boundaries in-
dicate that more dislocations tangled here after the deformation,
To understand the deformation mechanism underlying the ex-
which suggests that the cell boundaries play a critical role in im-
cellent mechanical properties of the as-annealed alloy, TEM obser-
peding the motion of dislocations. Similar microstructures that can
vations on the deformed microstructure of the as-built alloy and
hinder the movement of dislocations always play a positive ef-
fect on the strength, such as grain boundaries and interfaces be-
the as-annealed alloy were conducted.
tween phases [53]. As shown in Fig. 10(b), the planar disloca-
The microstructure of the as-built alloy after the deformation
tion configuration is composed of slip bands along {111} planes
at 298 and 77 K is shown in Fig. 10. Compared with the mi-
while no deformation twin (DT) and stacking faults (SFs) are ob-
crostructure before the deformation shown in Fig. 4(a, b), the den-
served in the as-built alloy deformed at 298 K, indicating that pla-
sity of dislocations inside cellular structures distinctly increases as
nar dislocation glide is the main deformation mechanism. While
Fig. 10(a) shows, suggesting a massive dislocation multiplication

ett.
Journal of Materials Science & Technology 197 (2024) 247-264
(a)
(b)
As-annealed 77 K
Engineering stress (MPa)
As-built 298 K
(MPa)
As-annealed 298 K
As-built 77 K
As-annealed298 K
As-annealed 773K.
rate
(MPa)
As-annealed 77 K
As-annealed 873 K
As-built 77 K
pae30p3
As-annealed 773 K
As-annealed 873K
True stress
As-built 298 K
Engineering strain (%)
True strain (%)
(c)
(d)
This work

## 77. K

## 298. K

SLM CoCrNi
Total elongation (
SLM (CoCrNi)94TizAl3 solid solution
Total elongation
SLM (CoCrNi)94TiAl3
SLM Fe28Co29.5Ni27.5Ti8.5Al6.5
SLM (FeCoNi)86Ti7Al7
SLM FeCoCrNiMn
SLM FeCoCrNiMn-TiC
SLM FeCoCrNiMn
Directly energy deposition (DED) FeCoCrNiMn
SLM FeCoCrNi
Ultimate tensile strength (MPa)
SLM Ni30C030Cr10Fe10Al18W1Mo1
(e)
(f) 1s00
DED Inconel718
SLM Inconel 718
Ultimate tensile stress (MPa)
Yield strength (MPa)
SLM Inconel 718
SLM Inconel718
SLM Alloy 625
DED 316 L steel
DED 316 L steel
DED 316 L steel
SLM 316 L steel
SLM 316 L steel
SLM 316 L steel
SLM AISI 4140 steel
Temperature (K)
Fig. 9. Mechanical properties of the AMed Co42Cr20Ni3oTi4Al4 alloy. (a) Representative tensile engineering stress-strain curves for the present alloy tested at 77, 298, 773,
and 873 K, respectively. (b) True stress-true strain curves and corresponding strain-hardening rate curves at 77, 298, 773, and 873 K, respectively; the solid lines are true
stress-true strain curves, and the dots represent the strain-hardening rate. The mechanical properties of the current as-annealed alloy and some reported AMed alloys tested
at (c) cryogenic temperature, (d) room temperature, and (e, f) elevated temperatures are compared.
g=002
(d)
(200)M
(111)T
(111)M
(200)T
(111)M
(111)T
Z[011]
g=002
Fig. 10. TEM observations of the microstructures of the as-built alloy after the deformation at (a, b) 298 K and (c, d) 77 K: (a) Two-beam BF TEM image showing the
bands along {111} planes; (c) two-beam BF TEM image showing SFs on the {11} planes; (d) DF TEM image of DTs and the corresponding SAED patterns (the inset).

Journal of Materials Sclence U Ittl
a)
-
g
g=002
P
DR
Q
P
*
-
FCC
APB
nm
L12
SF network
f)
RMS
.
SF
g=002
V
SE
V c1ock
-
SF
+
Fi. 11.Typical deformation substructures in the (a) CP region and (b) DP region of the as-annealed alloy deformed at 298 K, (c, d) the CP region, and (e, f) the DP region
of the as-annealed alloy deformed at 77 K: (a) two-beam BF TEM image of the intersecting SFs; (b) two-beam BF TEM image of the SFs extending in one direction; (c)
BF TEM image (left) of the intersecting slip bands and the corresponding DF TEM image (right); (d) the HR-TEM image of the L12 precipitate sheared by the SF and the
subsequently formed APB with an enlarged view (the inset); (e) two-beam BF TEM image of the intersecting SFs and the SF network; (f) the HR-TEM image exhibiting an
L-C lock generated by two intersected SFs.
at 77 K, a large number of SFs and DTs are observed in the as-
Fig. 12 shows the microstructures of the as-annealed alloy after
built alloy after deformation, as illustrated in Fig. 10(c, d). A sim-
tensile tests at elevated temperatures of 773 and 873 K. Generally,
ilar phenomenon has been observed in the other CoCrNi-based
the density of SFs decreases while tested at 773 K. Scattered and
MPEA [30,54-56]. The activation of SFs and DTs could effectively
short SFs can be observed in the CP region as Fig. 12(a) shows. The
relieve the stress concentration, and the newly formed SFs and
number of intersecting SFs also decreases, but they can still be ob-
DTs could further impede the motion of dislocations, thus both
served in a few DP regions (Fig. 12(b)). As for the alloy tested at
the ductility and strength of the as-built alloy are improved at

## 873. K, no intersecting SFs is observed, and the density of SFs fur-

## 77. K. The tendency of activating SFs and DTs at cryogenic tem-

ther decreases in both the CP and DP regions, as shown in Fig. 12(c,
peratures is ascribed to the SFE which decreases with decreasing
d).
temperature.
Fig. 11 shows the microstructure of the as-annealed alloy after

## 4. Discussion

deformation at 298 and 77 K. Generally, planar dislocation glide
is the main deformation mechanism. At 298 K, SFs can be acti-

## 4.1. The formation of the heterogeneous microstructure

vated in two {111} planes in the CP regions, intersecting with each
other severely, as the arrows indicated in Fig. 11(a). But in DP re-
As the microstructure characterization presented in Section 3.1,
gions, more SFs extend in one direction (Fig. 11(b)). A similar phe-
the as-annealed alloy exhibits a heterogeneous microstructure
nomenon has been reported by Zhao et al. [54], and it is ascribed
composed of a partially recrystallized matrix and the heteroge-
to the difference in precipitate morphology between CP and DP re-
neously precipitated L12 phase, which can also be categorized into
gions. At 77 K, a high density of intersecting slip bands shown in
CP regions and DP regions. The formation mechanism of both re-
Fig. 11(c) indicates the severe deformation dominated by the pla-
gions during the annealing is discussed below.
nar glide at the CP region. Fig. 11(d) presents the L12 precipitate
The DP behavior is closely related to the migration of reac-
sheared by SF, forming an APB. While at the DP region, SFs are also
tion fronts (RFs). The residual strain in the as-built alloy provides
activated in two {111} planes, and the intersection between SFs is
a sufficient driving force for the activation of the recrystallization
significantly enhanced, forming SF networks as shown in Fig. 11(e).
[43], thus promoting the bulging and migration of grain bound-
Furthermore, the mutual interaction between the SFs leads to the
aries (GBs), making them ideal RFs. Comparing Fig. 2(a, c), many
formation of sessile dislocations, which are generally called Lomer-
newly formed fine grains are distributed around the melting track
Cottrell locks (L-C locks) [57] as Fig. 11(f) shows.
regions, indicating that recrystallization is inclined to begin around

(a)
(b)
g=002
M
S
X
T
Moita
C
nm
nm
(d)
a
A
g=I11
g=002
M
Ptinsie
Bsicdo
.
X
S
as-annealed alloy deformed at 873 K.
(a)
Grain Boundaries
2°-10°
>10°
(c)
(d)
2.0
Cumulative misorientation ()
1.8
1.6
Misorientation (°)
1.4
1.2
1.0
0.8
0.6
0.4
0.2
0.0
um
Distance (μm)
Fig. 13. (a) IPF map of the as-built alloy from the XY plane (step size = 0.05 µm); (b) KAM map of the region corresponding to (a); (c) KAM figure from point to point
corresponding to the arrow in (b); (d) cumulative KAM figure corresponding to the arrow in (b); (e) BSE observation of the as-annealed alloy from the XY plane showing the
bulging of GBs.
boundaries. Except for those high-angle grain boundaries (HAGBs),
tours of cellular boundaries. The point-to-point (Fig. 13(c)) and cu-
there are also many low-angle grain boundaries (LAGBs) and cellu-
mulative (Fig. 13(d)) changes of the orientation along the marked
lar boundaries in the intra-granular region. There are three general
line in Fig. 13(b) indicate that neither the orientation gradient be-
recrystallization nucleation mechanisms: strain-induced boundary
tween cells nor the long-range orientation gradient is substan-
migration (SIBM), sub-grain coarsening, and sub-grain coalescence
tial. Therefore, it is reasonable that the recrystallization in the as-
[58]. The SIBM originates from HAGBs, while sub-grain coarsen-
annealed alloy mostly originates from the HAGBs, which is consis-
tent with the bulging of GBs in the as-annealed alloy (Fig. 13(e)).
ing and sub-grain coalescence are involved with the production of
During the DP process, the bulging GBs keep advancing into
HAGBs starting from LAGBs. However, the production of HAGBs by
the original grains, and dislocations composing cellular boundaries
the movement of sub-grain boundaries needs enough orientation
are eliminated after GBs sweep over. The bulging GBs are also
gradient [59]. Fig. 13(a, b) shows an area from the XY plane of the
short-circuit diffusion paths for solutes and preferable nucleation
as-built alloy where KAMs are distinct enough to show the con-

Journal of Materials Science & Technology 197 (2024) 247264
(a)
(b)
E
"
(d)
-
:
C
stage of the annealing; (d) the DP region in the late stage of the annealing; (e) the enlarged view of the CP region in the late stage of the annealing.
sites for the L12 phase. Once the nucleation of the L12 phase hap-
precipitation (CP) regions, making the discussion about whether
pens on the migrating grain boundaries, the precipitates will pin
the as-annealed alloy is a heterostructured material necessary.
on the GBs. The boundary segments between the pinning precip-
It is noteworthy that not all materials with heterogeneous mi-
itates keep bowing out due to the thermal activation. Meanwhile,
crostructure can be regarded as heterostructured materials. Zhu
the precipitates keep growing on the original pinning spots with
et al. [62] indicate that heterostructured materials consist of het-
the aid of rapid solute transporting from moving GBs, leading to
erogeneous zones with dramatic (> 100 %) variations in mechani-
the lamellar or short-rod morphology [60,61]. At the initial stage,
cal and/or physical properties and the interaction in these hetero-
the movement of bulging GBs is relatively fast, and the diffusion
zones produces a synergistic effect where the integrated property
of solutes is limited, so the size of discontinuous precipitates in
exceeds the prediction by the rule-of-mixtures. To figure out the
the intra-granular regions is smaller (about ~20 nm). It should be
difference in the strength of regions in the materials, nanoinden-
noted that the elemental segregation along cellular boundaries is
tation tests were conducted on the XY plane and XZ plane of the
continuously promoted as the annealing process begins. The Ni, Ti,
as-annealed alloy. 100 points were measured on each sample. The
and Al segregating along the original cellular boundaries may not
microstructure around each single nanoindentation was identified
be completely consumed by the rapid DP. Therefore, more L12 pre-
via SEM, and microstructures were classified into three categories:
cipitates form at the original cellular boundaries, though disloca-
(1) Grains with continuous precipitates; (2) coarse recrystallized
tion walls have annihilated. When the recrystallization comes to
grains with discontinuous precipitates; (3) fine recrystallized grains
the late stage, the advance of GBs slows down, and there would be
with discontinuous precipitates, which are shown in Fig. S6. More
more time for the diffusion and accumulation of solutes, so precip-
details about the three categories of microstructure are also pre-
itates near GBs exhibit larger sizes, and no cellular contour com-
sented in Section 7 in Supplementary Information. The average
posed of precipitates can be observed (as shown in Fig. S4).
Vicker hardness of these three kinds of microstructures on the XY
Meanwhile, without bulging GBs sweeping into the intra-
plane and XZ plane is quite close, as shown in Fig. S7, indicating
granular regions, the cellular structures made up of dislocations
the as-annealed alloy in our work can be regarded as the conven-
are retained, and CP dominates in the non-recrystallized grains.
tional alloy.
During the annealing process, the elemental segregation is con-
The contribution of cellular structures is another controversial
tinuously enhanced, so more L12 precipitates form along cellu-
issue. The cellular structures are known to play a critical role in the
lar boundaries, and L12 precipitates in the intra-cellular regions
optimization of mechanical properties of FCC structure alloys fab-
slowly grow up to an average size of ~10 nm. The evolution of
ricated by selective laser melting. Earlier studies indicated that the
the microstructure during the annealing can be illustrated in the
strengthening effect of the cellular structures is Hall-Petch type
schematic drawing in Fig. 14.
[63]. However, it is found that the strength is independent of cell
size, and dislocation densities of the alloy have been identified

## 4.2. Strengthening mechanism

as the dominant factor in strengthening [64]. Some studies indi-
cated that the strengthening effect of cellular structures is some-
how conditional [65]. Cellular structures may be sufficiently strong
In our current works, grains exhibit heterogeneous grain sizes
resulting from partial recrystallization. Except for the grain sizes,
against dislocation penetration and hence, behave like HAGBs, re-
the sizes of L12 precipitates and dislocation densities differ in
sulting in the Hall-Petch strengthening manner. Alternatively, they
grains in discontinuous precipitation (DP) regions and continuous
can be weak and only act as dislocation bundles when interacting

J. Huang, W. Li, T. Yang et al.
Journal of Materials Science & Technology 197 (2024) 247264
with moving dislocations, resulting in a dislocation-like strength-

## 7.49. % and 2.07 %, respectively. εs is the interaction factor. εG and

ening manner. As Fig. 10(b) shows, the cellular boundaries com-
εa are interaction parameters that are related to elastic size mis-
posed of tangled dislocations may decompose at high strain, indi-
match and atomic mismatch, respectively. Compared with εa, the
cating the cellular boundaries in the as-built alloy are not as strong
effect of εG is negligible, so the εs can be generally treated as 3εa,
as grain boundaries. The KAM map of the as-built alloy shown in
σss can be approximately regarded to be proportional to c1/2.
Fig. 13(b) suggests that the cellular boundaries here can only cause
The Δσ ss of the solid-solution-state (CoCrNi)94Al Ti3 alloy was es-
limited local misorientations, which cannot be even regarded as
timated to be ~49 MPa [54]. Hence, the strengthening effect of
LAGBs. Therefore, the contribution of cellular boundaries here is
solid-solution (Δo ss) for as-built and as-annealed alloys is calcu-
attributed to the dislocation hardening.
lated to be 61.2 and 16.9 MPa, respectively, indicating the solid-
Based on the microstructural characterization, the increase in
solution hardening contribution is quite limited.
the yield strength of the as-annealed alloy can be ascribed to the
The strengthening contribution from grain boundaries (Δσgb)
contribution of solid solution hardening (Δσss), grain boundary
can be calculated by using the classical Hall-Petch formula:
hardening (Δσgb), dislocation hardening (Δσdis), and precipita-
(6)
Δg = b · −1/2
tion hardening (Δσppt), in addition to the matrix friction stress
(o fr). Therefore, the yield strength of the as-built alloy and the
where kgb is the strengthening coefficient, and d is the average
as-annealed alloy at 298 K can be demonstrated by the following
grain size. kgb = 568 MPa µm−1/2
[54], and the average grain size
equation:
for the as-built and as-annealed alloy is 11.9 and 3.5 µm, respec-
tively. Thus, Δσ gb for the as-built and as-annealed alloys are cal-
(1)
σy−as built=fr + Δσ ss + Δσ gb + Δσ dis,
culated to be 164.3 and 303.6 MPa, respectively.
The o dis can be estimated by the following equation [68]:
(2)
σy-as annealed = σfr−matrix + Δσs + Δσ gb + σdis + σppt,
Δσdis = MαGbρ1/2,
(10)
For the as-built alloy, the friction stress (σ fr) is determined as

## 218. MPa by using the friction stress of the equiatomic CoCrNi alloy

2θ
(11)
[66]. For the as-annealed alloy,ofr-matrix should multiply the vol-
ρgNd =
. qn
ume fraction of the FCC matrix phase (fmatrix).
where α = 0.2 for FCC metals [69]; b is the Burgers vector
(3)
fr−matrix = r · matrix,
(b = 0.2532 x 10-9 m for the as-built alloy, and b = 0.2527 x
10-9 m for the as-annealed alloy, which are calculated from the
matrix = 1 - ppt,
(4)
XRD pattern). ρ represents the density of GNDs. θ is the KAM
value obtained from the KAM maps, here we use the average of
(5)
KAM values acquired from the XY plane and the XZ plane of the
ppt = PDp · dp + Pcp · fcp.
where fppt is the volume fraction of precipitates. Ppp is the volume
θas—annealed = 0.395°. µ is the unit length for EBSD characteriza-
fraction of the discontinuous precipitation region to the whole ma-
tion, here µ = 0.2 µm. Based on KAMs, the dislocation density is
trix, and Pcp is the volume fraction of the continuous precipitation
calculated: ρas-built = 3.10 × 1014 m-2, and ρas—annealed
= 2.73 x
region to the matrix. fdp is the volume fraction of discontinuous

## 1014. m-2. Hence, Δσ dis for the as-built and as-annealed alloys are

precipitates in the discontinuous precipitation region, fcp is the vol-
calculated to be 242.0 and 225.4 MPa, respectively.
ume fraction of continuous precipitates in the continuous precipi-
The Δσ ppt is given by the ordering strengthening [70]:
tation region.
1/2
PDp and Pcp are estimated to be 77.6 % and 22.4 % via SEM fig-
3πf
YAPB
(12)
Δσppt = 0.81M
ures, respectively. fdp is calculated to be 28.3 % by using the lever
2b
rule. However, continuous precipitates are too small to attain re-
liable chemical composition via TEM. The previous study indicates
where f is the volume fraction of precipitates, f = 28.3 %; is
that the difference in volume fractions of L12 precipitates in differ-
the antiphase boundary energy, here YApB = 143 mJ m-2 [6]. There-
ent regions of the heterogenous matrix is less than 2 % [6]. Hence,
fore, the Δσppt at 298 K is calculated to be 404.8 MPa.
the fcp is regarded to be equal to 28.3 %. It follows that fppt and
According to the investigation on the yield strength at different
matrix are 28.3% and 71.7 %, respectively, thus σfr-matrix = 218 x
temperatures, the friction stress of the matrix versus temperature
can be expressed as [2]:

## 71.7. % = 156.3 MPa.

The strengthening effect from solid-solution (Δo ss) can be cal-
2G
-2πω0
(13)
culated by the standard model based on the interactions between
σ(T =
exp
. exp

## 1. -v

b
bTm
dislocations and the substitutional solute atoms [3]:
3/2 . 1/2
where v is the Poisson's ratio, ωo is the dislocation width at 0 K,
G. εs
(6)
Δσss = M
b is the Burgers vector, T is the testing temperature, and Tm is the
melting temperature. Note that b is regarded as the temperature-
independent term since the change of b with temperature is very
EG
-3ε
(7)
ε =
small. However, Gfcc and v are temperature-dependent terms.

## 1. + 0.5εG

By using σfr (298 K) = 218 MPa, Gfcc(298 K) = 88.7 GPa,

## 1. ∂a

(8)
ν (298 K) = 0.314 [71], Tm = 1664 K [6], the ω0 is calculated to
Ea
=
m ∂
be 0.958b. At 77 K, Gfcc(77 K) = 93.5 GPa [67], v(77 K) = 0.308
[71], thus the σfr values for the as-built and as-annealed alloy are
where M is the Taylor factor, here M = 3.06 for FCC metals [3];
calculated to be 498.9 and 357.7 MPa, respectively.
G is the shear modulus, here G = 88.7 GPa (borrowed from the
Δσgb
and Δσppt are considered to be temperature-
equiatomic CoCrNi MEA [67]); am is the lattice constant of the ma-
independent for the as-built or the annealed specimens when
trix, here am = 0.357 nm (borrowed from the equiatomic CoCrNi
tested at 298 or 77 K, since the grain size and precipitate volume
MEA [67]); c is the molar ratio of the solute atoms, here c should
fraction are postulated to be fixed at these two test temperatures.
be the total molar ratio of Ti and Al. Based on the STEM-EDS mea-
For Δoss, if the change of εs with temperature is ignored, the
surement, on the as-built and as-annealed alloys, values of c are

σfr
σ ss

## 6. gb

σdis
dd
Experimental YS
Experimental YS (MPa)
Calculated YS (MPa)
404.8
255.1
404.8
237.6
164.0
242.0
64.5
225.4
242.2
164.0
17.8
498.9
242.2
61.2
357.7
16.9
218.0
156.3
as-built 298 K
as-built 77 K
annealed 298 K
annealed77 K
experimental values.
Δσss for as-built and as-annealed alloys are calculated to be 64.5
commodate plastic deformation by serving as Frank-Read disloca-
and 17.8 MPa, respectively. Δodis would also change with the
tion sources [57]. Furthermore, the APBs formed by the interaction
temperature due to the change of G. With the changed G, Δσdis
between SFs and L12 precipitates can act as barriers against dis-
at 77 K for the as-built and as-annealed alloy are calculated to be
location mobility, which can further increase the strain-hardening

## 255.1. and 237.6 MPa, respectively.

rate [76]. Hence, the as-annealed alloy shows the best synergy of
The contribution from all the strengthening effects mentioned
strength and ductility at 77 K, and a much higher strain-hardening
above is displayed in Fig. 15. The calculation results are well agreed
rate is obtained at 77 K in comparison with that at 298 K. When
with the experimental results. Precipitation hardening makes the
the test temperature increases to 773 and 873 K, the strength of
most contribution for the as-annealed alloy at 298 and 77 K, and
the as-annealed alloy decreases together with the density of SFs.
grain boundary strengthening and dislocation strengthening result-
Accordingly, the strain hardening rate of the as-annealed alloy
ing from additive manufacturing takes the second place, exhibiting
is SFs-mediated, which is closely associated with the SFE as the
the excellent combination of precipitation hardening and the ad-
following equation describes [77]:
vantage of additive manufacturing.
2ysF
(14)
tsF =
bp

## 4.3. Temperature-dependent strain-hardening rate

where YsF is the SFE, tsF is the critical resolved shear stress re-
The strain-hardening rate of the as-built and the as-annealed
quired for spontaneous partial dislocation separation and associ-
ated extended SF formation, and bp is the Burgers vector of a
alloy show evident temperature dependence, as presented in
Shockley partial dislocation. The stacking fault energy (ysf) of the
Fig. 9(b). For the as-built alloy, the planar dislocation glide is the
FCC matrix at 298 K can be estimated using the following equation
dominant deformation mode at 298 K. While at 77 K, a large num-
[78]:
ber of SFs are generated via dislocation dissociation, and DTs are
also activated. SFs and DTs provide more resistance to the disloca-
+2σFCC/HCP
(15)
tion slip by decreasing the mean free path of dislocations, which
is called the dynamic Hall-Petch effect [7274] so that the as-built
where n is the number of fault layers, i.e., n = 2 for an intrin-
alloy shows higher strain-hardening rate, strength, and ductility at
sic stacking fault, ρA is the molar surface density, ΔGFCC→HCP
is
the difference in Gibbs free energy of FCC and HCP phases, and

## 77. K.

FCC/HCP is the interfacial energy between FCC and HCP phases,
For the as-annealed alloy, the planar dislocation glide acts as
O
which is assumably 10 ± 5 mJ m-2 for transition metals [79]. For
the main deformation mechanism from 77 to 873 K, and no DT is
observed. The fully coherent interface between the high density of
{111}, ρA is defined as:
L12 precipitates and the FCC matrix can relieve stress concentra-
tion [10], providing a higher strain-hardening rate and maintain-
ρA=
$\sart}cc
(16)
NA$
ing a respectable uniform plastic deformation at the same time.
where aFcc is the lattice constant of the FCC phase, which is
The increase in the number of SFs at 77 K leads to a decreasing
SF spacing size and more SF networks, which are confirmed to be
as shown in Fig. S8, and NA is the Avogadro constant. Therefore,
significantly effective in impeding the movement of dislocations
and retaining strain-hardening [74,75]. On the other hand, the L-
ical composition-based thermodynamic calculation using Thermo-
C lock generated by the interactions between SFs can further hin-
Calc (TCHEA5 database), the left unknown parameter in Eq. (15),
der the moving dislocations and provide more dislocations to ac-

J. Huang, W. Li, T. Yang et al.
Table 2
from XRD of FCC and L12 phases.
UTS = 1586 MPa
Composition (at.%)
Lattice

## 150. mJ/m

Phase
(MPa)
constant
Co
YS = 1180 MPa
Cr
Ni
Al
Ti
(nm)
FCC
50.84
25.55
1.00
1.07
0.3571
21.54
L12
6SISF

## 100. mJ/m

16.01
4.38
59.12
9.77
10.71
0.3595

## 50. mJ/m²2

ΔG
FCC→ HCP
can be determined as follows:
G
FCC→ HCP
= GHCP GFCC = -755.808 - (-834.538)
= 78.73J mol-1
(17)
r (nm)
where GFCC and GHCP are the total energies of FCC and HCP struc-
tures based on the composition of the FCC phase in the current
Fig. 16. The estimated critical flow stress OsisF for the onset of SFs in the L12 phases
alloy, as listed in Table 2. By substituting Eqs. (16) and (17) as
with different ysisf vs. the dislocation separation distance (r).
well as other derived parameters into Eq. (15), YsF is estimated
as 25 ± 10 mJ m-2. At room temperature, this value may be too
high to activate twinning, but reasonably low enough to introduce
room temperature, thus the Osf also increases, leading to the de-
pronounced slip planarities such as SF networks and L-C locks in
creasing numbers of SFs and strain-hardening rate. Therefore, the
the FCC phase [80], which can be further confirmed by calculat-
as-annealed alloy exhibits a temperature-dependent strain harden-
ing the critically resolved shear stress (tsf) to initiate SFs in the
ing rate, which stems from the variation of SFE with temperature
matrix of the present alloy by Eq. (14). Here bp is the Burgers
[86,87].
vector of 1/6<112> partial dislocations (0.1458 nm). Thus, TsF is
However, it should be pointed out that the variation of SFE
computed to be 343 MPa, and the critical stress (σsF) is estimated
with temperature is not the only influence that decides the
to be 1043 MPa by multiplication of Taylor factor (M = 3.06 [3]),
temperature-dependent strain-hardening behavior of alloys. Pierce
i.e., σSF = Mt sF, which is well below the YS and flow stress of as-
et al. [88] reported that the increase in the SFE with the increas-
annealed alloy (1180 MPa), resulting in observed SFs at room tem-
ing temperature (from RT to 400 °C) of the Fe-22/25/28Mn-3Al-
3Si (wt%) alloys causes the transition from planar to wavy dis-
perature.
Additionally, the possibility of SFs penetrating through L12 pre-
location glide and the decrease in the work hardening rate from
cipitates in the as-annealed alloy at 298 K is theoretically evalu-

## 0. to 0.1 true strain when the twinning has not been activated,

ated as follows. Consider that L12 can be shorn by dislocations, i.e.,
which is consistent with the as-annealed alloy here. However, for
the flow stress is larger than the precipitate shearing stress (σ ppt
the mechanical twinning, although the critical resolved shear stress
= 405 MPa, which is calculated via Eq. (12)), which is also evi-
(CRSS) for mechanical twinning estimated from microstructure and
denced by TEM observation (Fig. S9), for most Ni-based and NiCo-
strain hardening behavior show substantial temperature depen-
based superalloys, a superlattice intrinsic stacking fault (SISF) may
dence, the increase in SFE with temperature had a rather minor in-
form when the L12 precipitate interacts with two 1/2<110> dislo-
fluence on the CRsS for twinning. The decrease in friction stress of
cations in the matrix according to the following equation [81]:
alloys with the elevated temperature is considered one of the rea-
sons for the late activation of twinning at elevated temperatures.
[121] + SISF +
The reducing friction stress is revealed to facilitate the cross slip
[011] +
[110]
[121]
(18)
I2
I3
|6
[89], which in turn reduces the local stress concentrations and de-
lays the initiation of mechanical twinning to higher normal stress
where the leading 1/3<112> dislocation enters the precipitate,
levels.
while a 1/6<112> is left at the interface. The corresponding re-
It is worth mentioning that mechanical properties at elevated
solved shear stress (tsisf) can be expressed by the following equa-
temperatures may also be affected by dynamic recovery (DRV) and
tion [82]
dynamic recrystallization (DRX). Fig. 17 shows the deformed mi-
Gsa}$
crostructure from the XZ plane of the as-annealed alloy tested at
Ysisf
(19)
tsisf =

## 773. K (Fig. 17(a, b)) and 873 K (Fig. 17(c, d)). The alloy tested at

b1
6π br(1− νs)

## 773. K exhibits a higher density of GNDs, which is consistent with

its better ductility. Compared with the microstructure before defor-
where YsisF is the SISF energy, b1 is the Burgers vector of the lead-
mation, the average grain sizes show little change, and the GNDs
ing 1/3<112> dislocation (0.2935 nm here), r is the dislocation
densities increase. The grain size distribution map and KAM dis-
separation distance, Gs, as, and νs are shear modulus (89.2 GPa
tribution maps are shown in Fig. S10. Moreover, both of the ten-
[83]), lattice constant (0.3595 nm here), and Poison's ratio (~0.2
sile curves tested at 773 and 873 K in Fig. 9 did not exhibit soft-
[84]) of the L12 phase, respectively. By taking the range of YsIsF
(from ~50 mJ m-2 for Ni-based to ~100−150 mJ m-2 for Co-based
ening before the fracture, indicating no evident DRX happens till
the fracture. Although DRX contributes little to the decrease of the
superalloys [85]) into account, the applied flow stress against r can
strength, the climbing of dislocations would be enhanced at ele-
be plotted using σsisF = MtsisF, as shown in Fig. 16, which in-
vated temperatures due to thermal activation, thus deteriorating
dicates that the SFs can be activated in L12 precipitates at room
the effect of dislocation strengthening and leading to the decreas-
temperature.
ing strength of the as-annealed alloy [23,59].
It has been reported that the SFEs of FCC alloys and MPEAs in-
The fracture surface of the tensile alloys tested at 773 and
crease with increasing temperature. At 77 K, the SFE is lower than

## 873. K exhibit mixed fracture mode (Fig. 18(a, e)). Dimples pre-

that at room temperature. The lower the SFE, the lower the σSF,
vail in a large area as Fig. 18(b, c, f, g) shows, which is consistent
so that more SFs are activated, forming SF networks and L-C locks
with the decent ductility. However, there are also typical cleavage
and leading to the ultra-high strain hardening rate. As tempera-
facets with intergranular cracks around (Fig. 18(d, h)), indicating
ture increases to 773 and 873 K, the SFE is higher than that at

Journal of Materials Science & Technology 197 (2024) 247264
(b)
Grain Boundaries

## 100. μm

20-100

## 100. μm

>100
(a)
(b)
(c)
Intergranular
cracks
um
e
g)

## 20. μm

## 200. μm

um
Fig. 18. SEM fractography of the as-annealed alloy tested at 773 K in (a), with the enlarged views shown in (b-d); at 873 K in (e), with the enlarged views shown in (fh).
that the coarse discontinuous precipitates along grain boundaries
Meanwhile, it has been reported that the twin initiation stress
are responsible for the decrease of elongation at elevated temper-
can also be affected by the grain size [96]. The relationship can be
atures [36,90]. It is noteworthy that the considerable decrease of
described by the following equation [97]:
elongation at intermediate temperatures commonly exists in poly-
kT
Y
σT = M
(20)
crystalline alloys, such as Ni-based superalloys, which are referred
+
bp
√d
to as intermediate-temperature embrittlement [91]. Intergranular
where OT is the critical twinning stress, M is the Taylor factor, γ
precipitates, grain boundary shearing or sliding, gas phase em-
is the SFE, bp is the Burgers vector of a partial dislocation, kT is
brittlement, decohesion of glide plane, dynamic strain aging, and
the Hall-Petch constant for twinning, and d is the grain size. Af-
grain boundary segregation of impurities are the main existing in-
ter the annealing, the average grain size decreases from 9.6 to
terpretations for the intermediate-temperature embrittlement. The

## 3.5. µm due to the recrystallization as shown in Fig. 2, thus the

coarse discontinuous precipitates along grain boundaries should
inhibition of DTs is enhanced due to the increased critical shear
not be the only reason for the intermediate-temperature embrittle-
stress. Furthermore, the drastically reduced channel width of the
ment of the as-annealed alloy, and the clarification of other mech-
FCC matrix due to the high density of L12 precipitates makes
anisms needs further studies in the future.
it even harder to activate DTs for the as-annealed alloy even at
No DT has been found in the C042Cr20Ni30Ti4Al4 MEAs after de-
cryogenic temperature, which is supported by other reported L12
formation, except for the as-built alloy deformed at 77 K, which is
precipitation-strengthened CoCrNi-based MEAs whose deformation
different from some CoCrNi MEAs and CoCrNiTiAl MEAs that are
are mainly SFs mediated [30,54,74,98]. Moreover, the L12-type pre-
dominated by DT at room temperature [30,54-56]. The activation
of twinning is often thought to be relevant to the low SFE [55,92].
cipitates possess much higher SFE compared to the FCC matrix, s0
It has been revealed that the addition of Ti and Al can increase the
that the incorporation of L12 precipitates would substantially in-
SFE of the alloy [93,94], making it more difficult to activate DTs at
crease the global SFE of the alloy, and subsequently increase the
room temperature for the as-built alloy which is in the solid so-
critical stress for twinning nucleation, leading to the suppression
lution state. However, when it turns to the cryogenic temperature,
of the DT initiation [74,99].
the SFE would decrease with the lower temperature as indicated
by previous studies [87,95], and more SFs contribute to higher flow

## 5. Conclusions

stress, making the activation of DT possible and finally leading to
In the present work, we successfully developed a precipita-
significantly improved ductility.
tion hardening C042Cr20Ni30Ti4Al4 MEA via SLM and the post-

J. Huang, W. Li, T. Yang et al.
Journal of Materials Science & Technology 197 (2024) 247264
heat treatment, exhibiting an excellent strength-ductility combi-
[5] X.H. Du, W.P. Li, H.T. Chang, T. Yang, G.S. Duan, B.L. Wu, J.C. Huang, F.R. Chen,
temperature-dependent strain-hardening rate were explored and
C.T. Liu, W.S. Chuang, Y. Lu, M.L. Sui, E.W. Huang, Nat. Commun. 11 (2020)
2390.
Luan,
X.K. Zhang,
discussed. The following conclusions can be drawn:
Chuang, J.C.
Huang, J.H.
W.P. Li, T.H. Chou, T.
Yang, W.S.
[6]
Appl.
Mater.
Today
. Du,
C.T. Liu,
F.R.
Chen,
X.F. Huo, H.J. Kong, Q.F.
He, X.H.
(1) The microstructures are composed of the partially recrystal-

## 23. (2021) 101037.

Wu,
Z.B.
Yang, J.H.
Luan,
lized matrix and heterogeneous precipitation of the L12 phase,
[7] I
L.Y. Liu, Y. Zhang, J.P. Li, M.Y. Fan, X.Y. Wang, G.C.
(2022) 103235.
Z.B. Jiao, C.T. Liu, P.K. Liaw, Z.W. Zhang, Int. J. Plast. 153
stemming from the concurrence of recrystallization and pre-
[8] L. Wang, X. Wu, Y. Wu, G. Liu, Z. Han, Y. Zhang, Y. Su, S. Kang, J. Shen, G. Zhang,
cipitation during the post-heat treatment. Discontinuous pre-
J. Mater. Sci. Technol. 149 (2023) 154-160.
Han,
Y.N. Su,
Y.D. Huang,
[9] L. Wang, X.Y. Wu, H.J. Su, B. Deng, G. Liu, Z.H. I
cipitation of the L12 phase takes place where recrystalliza-
)142917.
Y.P. Zhang, J. Shen, G.J. Zhang, Mater. Sci. Eng. A 840 (2022)
tion occurs, and continuous precipitation takes place at non-
D. Ponge,
[10] S.H. Jiang, H. Wang, Y. Wu, X.J. Liu, H.H. Chen, M.J. Yao, B. Gault,
recrystallized regions. Cellular boundaries composed of disloca-
D. Raabe, A. Hirata, M.W. Chen, Y.D. Wang, Z.P. Lu, Nature 544 (2017) 460-464.
Plast.

## 133. (2020)

[11] J. Li, H.T. Chen, Q.H. Fang, C. Jiang, Y. Liu, P.K. Liaw, Int. J.
tions are preferable nucleation sites for the L12 phase but do
102819.
not act as nucleation sites for the recrystallization as high-angle
[12] Y. Chen, Q.H. Fang, S.H. Luo, F. Liu, B. Liu, Y. Liu, Z.W. Huang, P.K. Liaw, J. Li,
grain boundaries due to the limited misorientations.
Int. J. Plast. 155 (2022) 103333.
[13] Y.L. Zhao, T. Yang, B. Han, J.H. Luan, D. Chen, W. Kai, C.T. Liu, J.J.
Kai, Mater.
(2) The as-annealed MEA exhibits a superiority of mechanical prop-
Res. Lett. 7 (2019) 152158.
erties over a wide temperature ranging from 77 to 873 K among
[14] B.X. Cao, W.-W.X.C.Y. Yu, S.W. Wu, H.J. Kong, Z.Y.
Ding,
T.L.
Zhang, J.H. Luan,
B. Xiao, Z.B. Jiao, Y. Liu, T. Yang, C.T. Liu, Acta Mater. 229 (2022) 117763.
the reported additively manufactured alloys, especially with an
[15] G. Laplanche, A. Kostka, C. Reinhart, J. Hunfeld,
G.
Eggeler, E.P. George, Acta
excellent YS of 1180 MPa, UTS of 1586 MPa with total elon-
Mater. 128 (2017) 292303.
gation of 22.7 % at 298 K, as well as an ultra-high YS of
[16] Z.J. Gu, Y.Z. Tian, W. Xu, S. Lu, X.L. Shang, J.W. Wang,
G.W.
Qin, Scr. Mater. 214
(2022) 114658.

## 1341. MPa, UTS of 1944 MPa with total elongation of 22.6 %

[17]
H.W. Deng, M.M. Wang, Z.M. Xie, T. Zhang, X.P. Wang, Q.F. Fang, Y. Xiong,
at 77 K. The synergy of precipitation hardening, grain bound-
Mater. Sci. Eng. A 804 (2021) 140516.
aries hardening, and dislocation hardening contributes to the
[18]
Kh. Moeinfar, F. Khodabakhshi, S.F. Kashani-Bozorg, M. Mohammadi, A.P. Ger-
lich, J. Mater. Res. Technol. 16 (2022) 1029-1068.
high yield strength, showing a successful combination of pre-
[19]
B. Blakey-Milner, P. Gradl, G. Snedden, M. Brooks, J.
. Pitot, E. Lopez, M. Leary,
cipitation hardening and additive manufacturing technology.
F. Berto, A.D. Plessis, Mater. Des. 209 (2021) 110008.
(3) Planar dislocation slip is the main deformation mechanism
[20]
B. Konieczny, A. Szczesio-Wlodarczyk, J. Sokolowski,
K.
Bociong, Materials
of the as-annealed MEA from 77 to 873 K. The decrease
(Basel) 13 (2020) 3524.
[21]
F. Haftlang, H.S. Kim, Mater. Des. 211 (2021) 110161.
of SFs with increasing temperature could be ascribed to the
[22] B.L. Han, C.C. Zhang, K. Feng, Z.G. Li, X.C. Zhang, Y. Shen, X.D. Wang, H. Kokawa,
SFE increasing with increasing temperature so that the strain-
R.F. Li, Z.Y. Wang, P.K. Chu, Mater. Sci. Eng. A 820 (2021) 141545.
hardening rate exhibits temperature dependency. The high
[23]
D.Y. Lin, X. Xi, X.J. Li, J.X. Hu, L.Y. Xu, Y.D. Han, Y.K. Zhang, L. Zhao, Mater. Sci.
Eng. A 832 (2022) 142354.
strain-hardening rate at 77 K results from the nano-spaced SFs
[24]
E.S. Kim, K.R. Ramkumar, G.M. Karthik, S.G. Jeong, S.Y. Ahn, P. Sathiyamoorthi,
networks, Lomer-Cottrell locks, and APBs, which are brought by
H.J. Park, Y.U. Heo, H.S. Kim, J. Alloy. Compd. 942 (2023) 169062.
the high density of SFs.
[25] J.M. Park, J. Choe, J.G. Kim, J.W. Bae, J. Moon, S.
Yang, K.T. Kim, J.-H. Yu,
H.S. Kim, Mater. Res. Lett. 8 (2020) 1-7.
(4) No substantial softening and DRX have occurred in the as-
[26] T. Fujieda, M.C. Chen, H. Shiratori, K. Kuwabara,
K.
Yamanaka, Y. Koizumi,
annealed alloy at elevated temperatures over 773 to 873 K. The
A. Chiba, S. Watanabe, Addit. Manuf. 25 (2019) 412420.
coarse discontinuous L12 precipitates along grain boundaries
[27] M. Song, R. Zhou, J. Gu, Z. Wang, S. Ni, Y. Liu, Appl. I
Mater. Today 18 (2020)
would induce the intergranular fracture, leading to premature
100498.
[28] F. Yang, L.L. Wang, Z.J. Wang, Q.F. Wu, K.X. Zhou, X. Lin, W.D. Huang, J. Mater.
tensile failure at 773 and 873 K.
Sci. Technol. 106 (2022) 128132.
(5) Compared to the as-built alloy at the state of solid solution, no
[29] T.W. Lu, N. Yao, H.Y. Chen, B.H. Sun, X.Y. Chen, S. Scudino, K. Kosiba, X.C. Zhang,
DT is found in the as-annealed alloy. It may be ascribed to the
Addit. Manuf. 56 (2022) 102918.
[30] N. Yao, T.W. Lu, K. Feng, B.H. Sun, R.Z. Wang, J. Wang, Y. Xie, P.C. Zhao, B.L. Han,
increasing critical twinning stress derived from the fine channel
X.C. Zhang, S.T. Tu, Acta Mater. 236 (2022) 118142.
width, small grain size, and the high SFE of the L12 phase.
[31] Y.K. Mu, L.H. H, S.H. Deng, Y.F. Jia, Y.D. Jia, G. Wang, Q.J. Zhai, P.K. Liaw, C.T. Liu,
Acta Mater. 232 (2022) 117975.
[32] X.L. Liu, G. Lindwall, T. Gheno, Z.K. Liu, Calphad 52 (2016)

## Declaration of Interest

125142.
[33] F. He, Z.J. Wang, Q.F. Wu, J.J. Li, J.C. Wang, C.T. Liu, Scr. Mater. 126 (2017) 1519.
[34] G. Bracq, M. Laurent-Brocq, L. Perriere, R.
Pires, J.M.
Joubert, I. Guillot, Acta
The authors declare that they have no known competing finan-
Mater. 128 (2017) 327336.
[35] Y.W. Wu, X.Y. Zhao, Q. Chen, C. Yang, M.G. Jiang, C.Y. I
cial interests or personal relationships that could have appeared to
Liu,
Z. Jia, Z.W. Chen,
T. Yang, Z.Y. Liu, Virtual Phy. Prototy. 17 (2022) 451-467.
influence the work reported in this paper.
[36] T. Yang, Y.L. Zhao, L. Fan, J. Wei, J.H. Luan, W.H. Liu, C. Wang, Z.B. Jiao, J.J. Kai,
C.T. Liu, Acta Mater. 189 (2020) 4759.
[37] M. Vittori, A. Mignone, Mater. Sci. Eng. 74 (1985) 2937.

## Acknowledgements

[38] J. Huang, W.P. Li, J.Y. He, R. Zhou, T.H. Chou, T. Yang, C.T. Liu, W.D. Zhang, Y. Liu,
J.C. Huang, Mater. Res. Lett. 10 (2022) 575584.
This study was financially supported by the National Natural
[39] D.X. Wei, X.Q. Li, J. Jiang, W.C. Heng, Y. Koizumi, W.M. Choi, B.J. Lee, H.S. Kim,
H. Kato, A. Chiba, Scr. Mater. 165 (2019) 3943.
Science Foundation of China (No. 52020105013).
[40] M. Komarasamy, S. Shukla, N. Ley, K.M. Liu, K. Cho, B. McWilliams, R. Brennan,
M.L. Young, R.S. Mishra, Mater. Sci. Eng. A 736 (2018) 383-391.

## Supplementary Material

[41] J.-W. Yeh, J0M 65 (2013) 17591771.
[42] X. Dong, Y. Zhou, Y.T. Qu, M.M. Wu,
Q.
Sun,
H.J. Shi, H.B. Peng, Y.X. Zhang,
S. Xu, N. Li, J.Z. Yan, Mater. Charact. 185 (2022) 111716.

## Supplementary Material

[43] S.B. Gao, Z.H.
Hu,
M.
Duchamp,
P.S.S.R.
Krishnan, S. Tekumalla, X. Song,
found, in the online version, at doi:10.1016/j.jmst.2024.02.077.
M. Seita, Acta Mater. 200
(2020) 366377.
[44] N. Ahmad, R. Ghiaasiaan,
P.R.
Gradl,
, S. Shao, N. Shamsaei, Mater. Sci. Eng. A

## 849. (2022) 143528.

References
[45]
K.G.E. Chlebus, B. Kunicka, J. Kurzac, T. Kurzynowski, Mater. Sci. Eng. A (2015)
647655.
J..Yeh, S.K., S.J. Lin, JY. an, T.S.Ci, T.T. S C.H. T S.Y.,
[46] V.A. Popovich, E.V. Borisov, A.A. Popovich, V.S. Sufiarov, D.V. Masaylo, L. Alz-
Adv. Eng. Mater. 6 (2004) 299303.
ina, Mater. Des. 131 (2017) 1222.
[47] Q. Teng, S. Li, Q.S. Wei, Y.H. Shi, J. Manuf. Process. 61 (2021) 35-45.
He, H. Wang, H.L. Huang, X.D. Xu, M.W. Chen, Y. Wu, X.J. Liu, T.G. Nieh,
[48] J.W. Lee, M. Terner, S.Y. Jun, H.-U. Hong, E. Copin, P. Lours, Mater. Sci. Eng. A
[3]
J.Y.
Lu, Acta Mater. 102 (2016) 187196.

## 790. (2020) 139720.

K. An, Z.P.
[49] G.M. Karthik, E.S. Kim, P. Sathiyamoorthi, A. Zargaran, S.G. Jeong, R.L. Xiong,
Y.L.
Zhao,
Y. Tong, Z.B. Jiao, J. Wei, J.X. Cai, X.D. Han, D. Chen, A. Hu,
[4]
T. Yang,
Liu, C.T. Liu, Science 362 (2018) 933-937.
S.H. Kang, J.-W. Cho, H.S. Kim, Addit. Manuf. 47 (2021) 102314.
J.J. Kai, K. Lu,
Y.

J. Huang, W. Li, T. Yang et al.
Journal of Materials Science & Technology 197 (2024) 247264
[74] T. Yang, Y.L. Zhao, J.H. Luan, B. Han, J. Wei, J.J. Kai, C.T. Liu, Scr. Mater. 164

## 748. (2019) 205212.

(2019) 3035.
[75] Y. Fang, Y.J. Chen, B. Chen, S.Z. Li, B. Gludovatz, E.S. Park, G. Sheng, R.O. Ritcie,
(2021) 141317.
Q. Yu, Appl. Phys. Lett. 119 (2021) 261903.
[76]
H.C. Liu, C.M. Kuo, P.K. Shen, C.Y. Huang, H.W. Yen, C.W. Tsai, Adv. Eng. Mater.
(2019) 275284.

## 23. (2021) 2100564.

[53]
L. Wang,
[77]
T.S. Byun, Acta Mater. 51 (2003) 3063-3071.
Intermetallics 118 (2020) 106681.
[78]
P. Adler, G. Olson, W.J.M. Owen, Metall. Mater. Trans. A 17 (1986) 17251737.
[54]
Y.L Zhao, T. Yang, Y. Tong, J. Wang, J.H. Luan, Z.B. Jiao, D. Chen, Y. Yang, A. Hu,
[79]
G.B. Olson, M. Cohen, Metall. Mater. Trans. A 7 (1976) 1897-1904.
C.T. Liu, J.J. Kai, Acta Mater. 138 (2017) 7282.
[80] S. Huang, W. Li, S. Lu, F. Tian, J. Shen, E. Holmström, L.J.S.M. Vitos, Scr. Mater.
[55] J.Y. Wang, J.P. Zou, H.L. Yang, X.X. Dong, P. Cao, X.Z. Liao, Z.L. Liu, S.X. Ji, J.

## 108. (2015) 4447.

Mater. Sci. Technol. 135 (2023) 241-249.
[81]
A. Suzuki, T.M. Pollock, Acta Mater. 56
(2008) 12881297.
[56] F. Weng, Y.X. Chew, Z.G. Zhu,
A. Suzuki,
M.J. Mills, T.M. Pollock,
, X.L. Yao, L.L. Wang, F.L. Ng, S.B. Liu, G.J. Bi, Addit.
[82]
M.S. Titus, A. Mottura, G.B.
Viswanathan,
Manuf. 34 (2020) 101202.
Acta Mater. 89 (2015) 423437.
[57]
[83] F. Pyczak, Z. Liang, S. Neumeier, Z. R
Rao, Metall.
Mater.
Trans. A 54 (2023)
M.W. Chen, Acta Mater. 144 (2018) 107115.
16611670.
[58]
E.F. Ferdinand Knipschildt, Mater. Sci. Technol. 38 (2022) 765779.
[84] Y. Liu, T. Ye, Q. Zhou, Y.
Wu, S. Duan, T. Fan, Z. Wang, P. Tang, Mater. Today
[59] F.J. Humphreys, M. Hatherly, Recrystallization and Related Annealing Phenom-
Commun. 31 (2022) 103655.
ena Elsevier, Amsterdam, Netherlands, (2012.) 250261.
[85] M.S. Titus, Y.M. Eggeler, A. Suzuki, T.M. Pollock, Acta Mater. 82 (2015) 530-539.
[60] I. Manna, S.K. Pabi, W. Gust, Int. Mater. Rev. 46 (2001) 53-91.
[86] J.K. Kim, J.H. Kim, H.J. Park, J.S. Kim, G.H. Yang, R. Kim, T.J. Song, D.W. Suh,
[61] S. Dasari, Y.-J. Chang, A. Jagetia, V. Soni, A. Sharma, B. Gwalani, S. Gorsse,
J.R. Kim, Int. J. Plast. 148 (2022) 103148.
A.-C. Yeh, R. Banerjee, Mater. Sci. Eng. A 805 (2021) 140551.
[87] M. Madivala, A. Schwedt, S.L. Wong,
F. Roters, U. Prahl,
W. Bleck, Int. J. Plast.
[62] Y.T. Zhu, K. Ameyama, P.M. Anderson, I.J. Beyerlein, H.J. Gao, H.S. Kim, E. Lav-

## 104. (2018) 80103.

ernia, S. Mathaudhu, H. Mughrabi, R.O. Ritchie, N. Tsuji, X.Y. Zhang, X.L. Wu,
[88] D.T. Pierce, J.T. Benzing, J.A. Jimenez, T. Hickel, I. Bleskov, J. Keum, D. Raabe,
Mater. Res. Lett. 9 (2021) 1-31.
J.E. Wittig, Materialia 22 (2022) 101425.
[63] T. Pinomaa, M. Lindroos, M. Walbruhl, N. Provatas,
A. Laukkanen, Acta Mater.
[89] S.I. Hong, C. Laird, Acta Metall. Mater. 38 (1990) 1581-1594.

## 184. (2020) 1-16.

[90]B.X. Cao, D.X. Wei, X.F. Zhang, H.J. Kong, Y.L. Zhao, J.X. Hou, J.H. Luan, Z.B. Jiao,
[64] Z. Li, B. He, Q. Guo, Scr. Mater. 177 (2020) 17-21.
Y. Liu, T. Yang, Mater. Today Phys. 24 (2022) 100653.
[91] L. Zheng, G. Schmitz, Y. Meng, R. Chellali, R. Schlesiger, Crit. Rev. Solid State 37
(2021) 207214.
S. Yoshida, T. Bhattacharjee, Y. Bai, N. Tsuji, Scr. Mater. 134 (2017) 3336.
(2012) 181214.
[66]
E.P. George, J. Alloy. Compd. 746 (2018) 244255.
[68]
U.F. Kocks, H. Mecking, Prog. Mater. Sci. 48 (2003) 171273.
[69] J. Su,
Acta Mater. 210 (2021) 116829.
D.
Raabe, Z.M. Li, Acta Mater. 163 (2019) 4054.
[95] D. Molnár, X. Sun, S. Lu, W. Li, G. Engberg,
Vitos,
Mater. Sci.
. Eng. A 759
[70]
A.J. Ardell,
Metall. Trans. A 16 (1985) 21312165.
L.
[71]
(2019) 490497.
866872.
[72]
O. Bouaziz, S. Allain, C. Scott, Scr. Mater. 58 (2008) 484-487.
[73]
Y. Tong, D. Chen, B. Han, J. Wang R. Feng, T. Yang, C. Zhao, Y.L. Zhao, W.Guo,
Sci. Eng. A 712 (2018) 603607.
Y. Shimizu, C.T. Liu, P.K. Liaw, K. Inoue, Y. Nagai, A. Hu, J.J. Kai, Acta Mater. 165
[98] Y. Xie, P. Zhao, Y.G. Tong, J.P. Tan, B.H. Sun,
, Y. Cui, R.Z. Wang, X.C. Zhang, S.T. Tu,
(2019) 228240.
Sci. China: Technol. Sci. 65
(2022) 17801797.
[99] A. Breidi, J. Allen, A. Mottura, Acta
Mater.
(2018) 97108.