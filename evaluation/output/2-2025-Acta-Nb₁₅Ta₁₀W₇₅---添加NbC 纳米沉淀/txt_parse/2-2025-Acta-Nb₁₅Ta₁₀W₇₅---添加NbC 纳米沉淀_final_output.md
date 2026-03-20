Simultaneous improvement of printability, mechanical isotropy, and high
temperature strength in additively manufactured refractory multi-principal
element alloy via ceramic powder additions and in-situ NbC
nano-precipitation
Ran Duan a, Yakai Zhao b,c, Xiaodan Li e, Jintao Xu a, Meng Qin a, Kai Feng
a,d,*
Zhuguo Li a,*, Beibei Xuf, *, Upadrasta Ramamurty
g
a Shanghai Key Laboratory of Materials Laser Processing and Modification, School of Materials Science and Engineering, Shanghai Jiao Tong University, Shanghai,
200240, PR China
b Future Energy Acceleration & Translation (FEAT), Agency for Science, Technology and Research (A*STAR), Singapore, 138634, Singapore
c Institute of Materials Research and Engineering (IMRE), Agency for Science, Technology and Research (A *STAR), Singapore, 138634, Singapore
d School of Materials and Energy Engineering, Guizhou Institute of Technology, Guiyang, Guizhou, 550002, PR China
eShenyang Aircraft Corporation, Shenyang, 110000, PR China
f State Key Laboratory of Materials for Integrated Circuits, Shanghai Institute of Microsystem and Information Technology, Shanghai, 200050, PR China

## 8. School of Mechanical and Aerospace Engineering, Nanyang Technological University, Singapore, 639798, Singapore

ARTICLEINFO

## ABSTRACT

## Keywords

The inherent brittleness of the refractory multi-principal element alloys (RMPEAs) renders manufacturing of
Refractory multi principal element alloys
structural components with complex geometries using conventional means difficult. The additive manufacturing
Laser powder bed fusion
technique of laser powder bed fusion (LPBF) can potentially circumvent this problem. However, eliminating
In-situ nano-precipitates
cracks, minimizing porosity, reducing the microstructural and (consequent) mechanical anisotropy, and
Printability
retaining high-temperature (HT) strength—all simultaneously—remain the key challenges. Adding ceramic
High-temperature strength
particles to the alloy can improve the printability and HT strength. However, the extreme melting points of
RMPEAs can lead to their dissolution. Keeping this in view, 1.5 at. % WC powder—determined theoretically to be
the optimum—was added to the Nb15Ta10W75 powders prior to LPBF. Results show an expanded process window
and improved printability, attributed to the enhanced laser absorptivity, without compromising powder flow-
ability. Carbon released through the dissolution of WC combines with Nb to form NbC in-situ, which promotes in
the columnar-to-equiaxed microstructural transition and hence reduced mechanical anisotropy. The NbC nano-
precipitates also enhance the high temperature strength (up to 1600 C) by hindering the mobility of both screw
and edge dislocations.

## 1. Introduction

to softening at HT, and HT strength (~400 MPa at 1600 °C), far
exceeding the service temperature of Ni-based superalloys [9]. While it
The advent of multi-principal element alloys (MPEAs) has opened
is particularly suitable for HT pressure-bearing components, its intrinsic
the arena of alloy design to a vast multicomponent space and enabled
brittleness severely limits the application potential as producing com-
the identification of alloys with prominent properties for various ap-
ponents with complex shapes is difficult [10]. The additive
plications[14]. Specifically, the refractory multi-principal element al-
manufacturing technique of laser powder bed fusion (LPBF) enables the
loys (RMPEAs) exhibit excellent high-temperature (HT) strength and
direct fabrication of such components, overcoming the limitations (such
resistance to HT softening, making them potential candidates in a wide
as restricted mold shapes and poor processability) of arc melting
variety of high temperature applications [58]. Among RMPEAs re-
[1113]. However, two critical challenges remain for LPBF of NbMo-
ported thus far, NbMoTaW exhibits promising phase stability, resistance
TaW. First, the inherent brittleness of NbMoTaW could induce cracking
*
Corresponding authors.
https://doi.org/10.1016/j.actamat.2025.121325
technologies.

under the high thermal gradients intrinsic to LPBF, making defect
difficult to achieve a large degree of ΔTcs. Adding suitable ceramic
elimination particularly challenging [14]. Second, columnar grains
particles, which would act as the heterogenous nucleation cites, is
preferentially form along the [001] or [101] crystallographic directions
essential for achieving the columnar to equiaxed transition (CET) in it
during LPBF, resulting in anisotropy that could adversely affect practical
[13]. Since the high MP of Nb15Ta10W75 can result in the dissolution of
applications [15,16]. These challenges are addressed—primarily—by
the added particles, the key strategy employed here is to add ceramic
adding low-melting-point elements or ceramic particles to RMPEAs.
powders that can dissolve in the melt pools and, in the process, intro-
Incorporating low melting point (MP) elements (e.g., Ti, Zr, or Hf
duce a non-metallic element to the melt, which subsequently
with the melting points of 1670, 1852, and 2227 C, respectively)
re-precipitate in-situ and regulates the grain morphology. The phase
significantly enhances the constitutional undercooling (∆Tcs). It, in turn,
stability of the in-situ formed precipitates is an additional consideration
provides the driving force for heterogeneous nucleation and thus sup-
that is crucial for maintaining grain morphology and strength of the
presses the columnar grain growth during LPBF [17,18]. However,
alloy at HT. To this end, the solid solubility and melting points of various
alloying with elements with lower MP reduces the plastic flow softening
in-situ precipitations were assessed using an equilibrium phase diagram
temperature and promotes the transition of dislocation-mediated plastic
obtained from the Thermo-Calc software. An example of it is displayed
deformation from that governed by cross-kinking to that of diffusion,
in Fig. 1(a). It shows that with the incorporation of 0.25 at. % C into
thereby adversely affecting the HT strength [19-21]. It also could
Nb15Ta10W75, the matrix phase with the body centered cubic (BCC)
adversely affect the printability during LPBF. The significant thermo-
crystal structure first solidifies, followed by the metal carbide (MC)
dynamic differences (e.g., melting point, viscosity, and thermal expan-
phase at 2613 °C, with a maximum molar fraction of 1.1 %. Similar
sion coefficient) between the high and low MP elements narrow the
equilibrium phase diagrams were obtained when C, N, B, or O in
processing window and increase the risk of segregation-induced
different proportions were introduced into Nb15Ta10W75, which all
cracking owing to the increased volatility of low MP elements [2123].
consist of BCC phase and in-situ precipitates (MC, MN, MB, or MO,
The addition of ceramic particles to alloys during LPBF can enhance
respectively). The precipitation temperatures of MC, MN, MB, and MO
heterogeneous nucleation, suppress columnar grains, and hinder dislo-
are displayed in Fig. 1(b), and the maximum re-precipitation contents
cation mobility during HT deformation of the alloy [24]. The ceramic
after adding different contents of C, N, B, or O into Nb15Ta10W75 matrix
particles can also improve printability through the following possible
are shown in Fig. 1(c). The MC phase has the highest precipitation
mechanisms. They could (i) refine grains, which could help resist crack
temperature (the best phase stability) and re-precipitation content (the
formation [25], (ii) lower the melt viscosity, which would promote the
lowest solid solubility) compared to the MN, MB, and MO type pre-
molten metal flow in filling the pores [26], (ii) enhance wettability that
cipitates. Therefore, it is inferred that adding C to Nb15Ta10W75 aids in
would facilitate stronger interlayer bonding [27], and (iv) alleviate the
the in-situ formation precipitates and contributes to the phase stability.
tensile stresses generated during solidification by ceramic-induced
To ensure the in-situ MC precipitation during LPBF, the non-
compressive stress to suppress cracking [28]. The effectiveness of
equilibrium solidification paths of (Nb15Ta10W75)100xCx (x = 0, 1.0,
these mechanisms depends critically on the survival of ceramic particles

## 1.5. at. %) at a cooling rate of 107 K/s were estimated using the Gulliver-

within the melt pools of LPBF, as the high MP of RMPEA poses the risk of
Scheil model module (available in the Thermo-calc software) to deter-
mine the amount of C that needs to be added. Results are displayed in
ceramic particle dissolution.
Keeping the above in mind, this work selectively incorporates nano-
Figs.1 (d1-d2). The Gulliver-Scheil model is suitable for simulating the
sized carbide particles into Nb15Ta10W75 powders to improve print-
non-equilibrium solidification process that occurs under the rapid so-
ability by enhancing laser absorptivity. It also utilizes in-situ precipita-
lidification conditions which prevail during the LPBF process [30]. This
model assumes that complete diffusion occurs within the liquid phase,
tion during LPBF to reduce the anisotropy and improve the room
temperature (RT)/HT strengths. The roles of carbide particles and in-situ
while no diffusion occurs in the solid phase [30]. Figures.1 (d1-d2) show
that the solidification sequence remains liquid (L)→ BCC phase as long
precipitates are further summarized in Supplementary-Note 1. This
strategy effectively addresses the thermal stability limitations of ceramic
as the added C content is below 1.5 at. %. It changes to L→ BCC→
BCC+MC when more than 1.5 at. % C. Therefore, incorporating more
particles in improving printability and HT strength in RMPEAs.
Nb15Ta10W75 alloy was chosen as the matrix, as it was optimized from
than 1.5 at. % C to Nb15Ta10W75 is deemed beneficial for in-situ MC
the Nb-Mo-Ta-W alloy systems using the Toda-Caraballo model and
precipitation during LPBF.
While increasing the C content beyond 1.5 at. % can contribute
demonstrated to exhibit an excellent HT strength of 640 MPa at 1600 C
positively to the precipitate formation during LPBF, it also could
[29]. The selection of ceramic particles involved the following three
adversely affect the powder flowability, as it reduces the smoothness of
steps. (i) The type of non-metallic element within ceramic particles was
the powder surfaces and thus enhances the rolling friction between the
determined by evaluating the solid solubility and melting point (ob-
powder particles [31]. For determining the optimal type of carbide
tained from the equilibrium phase diagram) of its in-situ formed com-
ceramic additions, the flowability and laser absorptivity of Nb15Ta10W75
pounds. (ii) The optimum ceramic content to be added was determined
powders mixed with different ceramic powder contents were assessed.
based on the critical re-precipitation amount (obtained from the
The detailed selection process is shown in Supplementary-Note 2, and
non-equilibrium solidification path calculations) to ensure in-situ
only the best results are presented below.
nano-precipitate formation during LPBF. (iii) The ceramic type was
The required quantities of elemental powders (Nb, Ta, W, > 99.9 %
selected by evaluating mixed powder characteristics (including laser
purity, Xiamen Tungsten Co.,Ltd., China) for forming Nb15Ta10W75 were
absorptivity and flowability), which can minimize the impact of the
accurately weighed using an electronic analytical balance. The pre-
ceramic addition on the powder spreading characteristics and improve
mixed powders were put into a mixing tank and evacuated to a vac-
printing quality. The formation mechanisms of the NbC
uum of 10-1 Pa before filling it with the argon gas. The pre-mixed
nano-precipitates, as well as their effects on microstructural evolution
powder was then mixed at 120 r/min for 6 h in a three-dimensional
and RT/HT mechanical properties, were investigated in detail. Notably,
(3D) planetary mill. A laser diffraction analyzer (DC24000 UHR, CPS,
the impact of NbC nano-precipitates on the screw/edge dislocation
Inc.) was used to measure the equivalent diameter of the powders. The
mobility at high temperatures is evaluated.
D10, D50, and D90 of the Nb15Ta10W75 powders were 20, 37, and 57 µm,
respectively. The powders display a spherical morphology, as shown in

## 2. Materials and methodologies

Figs.2 (a1) and (b1). Then, WC powder was added to the Nb15Ta10W75
powder such that the C content in the combined alloy corresponds to 1.5

## 2.1. Material design and powder mixing

% of the total at %; this alloy is referred to as (Nb15Ta10W75)98.5C1.5
hereafter. The WC powder size follows the Gaussian distribution and
Since MPs of all the elements in the Nb15Ta10W75 alloy are high, it is

Selection of non-metallic
Equilibrium phase diagram
element contents
element types
(a)
(d1)
(b)
Carbon addition of 0.0
%
O
(°C)
1:Liquid ←→
BCC
Molar ratio of phase
BCC
Temperature
1.1
MC
Liquid
0.0
MC

## 1000. 1500 2000 2500 3000 3500

MN
MB
MO
Temperature (C)
(c)16F
(d2)
-MC
Carbon addition of 1.5
%
Molar of phase (%)
(°C)
X
Xc
XN
X
Xo
MN
1:Liquid ←→ BCC
matrix
B

## 99.75. 9

## 0.25. %

MB
%

## 0.25. %

Temperature
2:Liquid ←→ BCC + MC

## 0.25. %

MO

## 99.25. %

## 0.75. %

## 0.75. %

## 98.5. %

## 1.5. %OR

## 1.5. %OR1.5 %

OR

## 1.5. %

## 97.0. %

## 3.0. %

## 95.0. %

## 5.0. %

None-metallic element content (%)
Mole fraction of solid (%)
Fig. 1. (a) Equilibrium phase diagram and element compositions of Nb15Ta10W75 doped with non-metallic elements. (b) Precipitation temperatures of MC, MN, MB,
MO. (c) Comparison of the molar fractions of different in-situ precipitated phases for different non-metallic element additions. Selection of non-metallic element
content based on the solidification path for (Nb15Ta10W75)100-xCx: (d1) x = 0 at. %; (d2); x = 1.5 at. %.
was found to be uniformly distributed on the surfaces of the
Lambda 950 Spectrophotometer, PerkinElmer, Inc.). The laser absorp-
Nb15Ta10W75 powders after being mixed in a planetary mill for 5 h, as
tivity of the (Nb15Ta10W75)98.5C1.5 powders is 88 % higher (at a wave-
shown in Figs. 2(a2) and (b2). The flowability of powders, which is
length of 1070 nm used for the LPBF process) than that of the
crucial for printing quality, was evaluated by using the Hall flowmeter
Nb15Ta10W75 powders, as shown in Figs.2 (d1-d2). Thus, incorporation
[32]. Both the Hall flow rate (HRF) and the angle of repose (AOR) did
of 1.5 at. % WC powders into Nb15Ta10W75 aids in the in-situ precipi-
not show significant changes after the incorporation of WC powders, as
tation as well as fabrication using LPBF.
shown in Figs.2 (c1-c2), indicating that it will not affect the powder flow
and spread.

## 2.2. Material preparation

Apart from powder flowability, laser absorptivity also significantly
influences print quality. The addition of smaller WC particles to the
The LPBF processes were carried in an SLM 280 metal printer (Zhong
Nb15Ta10W75 powder increases its convex and specific surface areas and
Rui Technique, China), which was equipped with a maximum laser
thus could enhance its laser absorptivity and reduce the energy required
power of 500 W (YAG fiber laser; beam spot diameter 90 µm; wave-
for melting powders [32]. To ascertain this, the laser absorptivity was
length 1070 nm). The process chamber was filled with high-purity argon
measured using the diffuse reflectance spectroscopy (DRS, UV-vis-NIR
(99.999 vol %; oxygen content below 100 ppm) and shielded the sam-
(a1)
Nb15Ta10W75
(b1)
(c1)
Nb15Ta10W75
HRF:7 s
8o
D90=57μm
Cumulative frequency
Relative frequency
22±0.2°
o
(d1).
D50=37μm

## 71. % (1070 nm)

Absorbance
D10=20μm
Wavelength (nm)
Powder diamerter (μm)
(a2)
(Nb15Ta10W75)98.5C1.5
(b2)4
WC
(c2)
HRF: 21s
%
D90=0.9 μm
Cumulative frequency
Relative frequency

## 30. ±0.8

D50=0.3 μm
Absorbance (%)
(d2)

## 88. % (1070 nm)

25:
WC
D10=0.1 μm

## 50. μm

## 5. μm

Powder diamerter (μm)
Wavelength (nm)
Fig. 2. Surface morphology of (a1) Matrix powders and (a2) Mixed powders; Particle size distribution of (b1) Matrix powders and (b2) WC powder additions; HRF and

ples from oxidation. A rotation angle of 67 between successive layers
testing machine, with a heating rate of 10 °C/min and a constant
was applied to reduce stress and anisotropy. A polished pure tungsten
displacement rate (εL) of 0.0025 mm/s. The size of HT compression
plate was used as the substrate to improve the bonding with the mate-
rial. The melting points of Nb, Mo, Ta, and W all exceeded 2400 °C [8],
specimens was $4 mm × 8 mm.
requiring high energy input to melt the powders during LPBF

## 3. Results

completely. To analyze the influence of WC powder addition on the
optimum printing process parameter window of Nb15Ta10W75, a series

## 3.1. Sample preparation

of samples were printed using different volumetric energy densities
(VED) [33]:
Results of the defect morphologies of the printed samples, charac-
terized using OM, and their relative densities, measured using a gas
P
VED=
(1)
expansion density tester, are shown in Fig. 3(a). For VED below 310
vht
Jomm-3, lack of fusion (LOF) pores were observed in both Nb15Ta10W75
In Eq. (1), P is laser power, v is the scanning speed, h is the hatch
and (Nb15Ta10W75)98.5C1.5. They are likely due to inadequate heat input
spacing, and t is the layer thickness. A total of 480 process parameter
for fully melting refractory metal powders [34,35]. When VED exceeded
combinations, with the VED and P ranges of 50 to 850 J/mm3 and 150 to

## 620. J•mm-3, cracks were observed in both RMPEAs. Cracking is thought

## 400. W, respectively, for each composition were explored. In all cases, t

to be driven by the accumulation of thermal stresses, caused by the
was fixed at 40 µm, while h was either 30 or 40 µm, v was adjusted
excessive energy input [23]. The optimal VED ranges for Nb15Ta10W75
accordingly based on the above parameters. Based on these trails, the
-3
and
and (Nb15Ta10W75)98.5C1.5 were found to be 520620 J•mm
following optimum process parameter combination for Nb15Ta10W75

## 360520. Jomm-3, which resulted in the densities of 99.2 ± 0.15 % and

was identified: P = 300 W, v = 400 mm/s, t = 40 μm, and h = 30 μm.

## 99.5. ± 0.1 %, respectively, with pores being the only type of defects

With the addition of 1.5 at. % WC powder, a v of 690 mm/s (while the
present in the blocks fabricated using these parameters. The incorpo-
other three process parameters remained the same) gave the best results.
ration of WC powders not only led to a higher density—that too at a
A gas expansion density tester (HX-TD, Hiseel, China) was used to
lower VED, but also a wider process window (extended by 50 Jomm-3),
measure the relative density of the printed samples. This device
compared to Nb15Ta10W75, possibly due to the enhanced laser absorp-
measured the variation in helium gas volume within the test chamber
tivity (Fig. 2(d2)). Cuboidal samples (8 × 8 × 10 mm3) of both the alloys
before and after placing the sample, providing an efficient, accurate, and
were manufactured with the optimal process (mentioned in Section 2.2)
non-destructive method to measure the true volume and density of the
and are used for microstructure characterization and compression ex-
printed samples. To ensure measurement accuracy, the printed samples
periments, as shown in Fig. 3(b).
were successively polished using the 500 #, 1000 #, 1500 #, 2000 # and

## 3000. # grit sandpapers to minimize the influence of irregular surface

## 3.2. Microstructural characterization

contours. For each printing parameter combination, nine samples were
printed, and their density was measured, with each sample tested 3
Nb15Ta10W75
and
The
XRD
patterns
obtained
on
times to ensure the reliability of the results. Cubic samples of 8 × 8 × 10
(Nb15Ta10W75)98.5C1.5 are shown in Fig. 4. The pattern obtained on
mm
were printed and used for density measurement, microstructural
Nb15Ta10W75 shows a single phase with the BCC crystal structure. With
characterization, and compression experiments.
the incorporation of WC powder, additional peaks corresponding to the
NbC precipitates with B2 crystal structure are observed. The dislocation

## 2.3. Microstructural and mechanical characterization

density (ρ) within the built samples was estimated using the XRD data
and the following equations [36,37]:
The crystal structure of the phase(s) in the microstructure was
2√39
(2)
analyzed by using the X-ray diffraction (XRD; D8 Advance Da Vinci,
ρ =
qsh
Bruker Corp., USA) equipped with Cu-Kα radiation (λ = 1.5418 Å)
operating at 40 kV, 40 mA, and performed over a scan range of 20 ° and
β
(3)

## 100. with a scan rate of 1.5 /min. The defect characteristics of the

=
4tanθ
printed samples were characterized using an optical microscope (OM;
Axio Imager A2m, Zeiss, Germany). Microstructural characteristics and
Kλ
(4)
ψs =
powder morphology were observed with the aid of a scanning electron
βcosθ
microscope (SEM; FEI Co., Hillsboro, OR, USA). It was equipped with the
where 9 is the micro-strain (which is related to the full width at half
energy dispersive spectroscopy (EDS) and electron backscatter diffrac-
tion (EBsD) detectors, which were used to analyze the microscopic
maximum (FWHM) of the XRD peak, β [38]), ψr is the coherent domain
segregation and the grain orientation, respectively. The EBSD experi-
size (that depends on the X-ray wavelength, λ = 0.15405 nm [38,39]), b
ments were performed at an accelerating voltage of 20 kV with a scan
is the Burgers vector, θ is the Bragg angle, and K is a dimensionless factor
(= 0.89 [39]). Details of the calculations used for estimating ρ based on
step size of 0.1 µm. The finer microstructures and precipitates were
the XRD data are provided in Supplementary-Note 3. The estimated ρ
observed by using transmission electron microscopy (TEM; JEM-F200X,
values in Nb15Ta10W75 and (Nb15Ta10W75)98.5C1.5 are about 3.36 ± 0.2
JEOL Ltd., Tokyo, Japan) working at a voltage of 200 kV. For TEM, foils
were prepared by a focused ion beam (FIB; Carl Zeiss AG) equipped with
× 1014
and 3.96 ± 0.3 × 101
m
, respectively.
an electron beam at 100 kV. The elemental distribution within the
Figs. 5 (a1-a4) display the SEM images of the X-Y and X-Z planes of
precipitates was characterized using the 3D-atom probe tomography
Nb15Ta10W75 and (Nb15Ta10W75)98.5C1.5. They show few pores and no
cracks, confirming the high relative densities and good quality prints.
(3D-APT; LEAP 5000X), operating at a pulse repetition rate of 200 kHz
and a UV laser energy of 60 pJ. The sharp tipped samples for 3D-APT
The inverse pole figure (IPF) maps (overlapped with the high-angle
were fabricated by annular milling within the grains using FIB.
grain boundaries (HAGBs) for showing grain morphologies) are dis-
played in Figs. 5 (b1-b4). Generally, the misorientation angles between
Uniaxial compression experiments were performed in a universal
neighboring grains exceed 15° for HAGBs, while the low-angle grain
testing machine (Sans Testing Machine Co., Ltd., Shenzhen, China)
boundaries (LAGBs) are those grain boundaries (GBs) with misorienta-
equipped with a video extensometer (LVE-MICRO30) at a nominal
tion angles between 2° and 15° [40]. In the X-Y plane, both the alloys do
constant loading rate of 0.008 mm/s. The size of compression specimens
not exhibit significant columnar grain morphology. In the X-Z plane,
was Φ2 mm × 4 mm. At least three samples were tested for each case.
Nb15Ta10W75 exhibits a columnar grain morphology, with the long axis
The HT compression properties were measured by using a Gleeble-3500

Nb15Ta10W75,
(Nb15Ta10W75)98.5C1.5
(a)
(b)
X

## 99.2. %

Density (%)
Cracks

## 99.1. %

Densit
Nb15Ta10W75,

## 10. 11 12

Pores
Building
Pores
Z
N+1
Direction
X
520-620 Jmm-3
mm
370-520 Jmm-3

## 1. mm

X
(Nb15Ta10W75)98.5C1.5
Laser energy density (Jmm")
Laser energy density (Jmm
experiments.
(e4)). Correspondingly, the MUD value decreased to 3.02.
Bz(NbC)
(Nb15Ta10W75)98.5C1.5
(110)
Bright-field (BF) TEM images obtained from the Nb15Ta10W75 and
Nb15Ta10W75
(Nb15Ta10W75)98.5C1.5 samples are shown in Figs.6 (a1) and (a2),
BCC
(Matrix)
respectively. (Nb15Ta10W75)98.5C1.5 contains a large number of
dispersed precipitates, which were uniformly distributed both within
Intensity
B
(NbC)
Intensity
the grains and at the GBs. Selected area electron diffraction (SAED)
patterns of Nb15Ta10W75, obtained using the [011]Bcc zone axis, and
(211)
(200)
(Nb15Ta10W75)98.5C1.5 along the [1-31]Bcc zone axis, are shown in Figs.6
(220)
(111)
(b1) and (b2), respectively. Nb15Ta10W75 exhibits only a BCC structure
without any second phase. In contrast, (Nb15Ta10W75)98.5C1.5 displays
an additional set of diffraction spots, which correspond to the B2 crystal
structure, indicating the in-situ formation of MC precipitates. The phase
2-Theta
structures observed from the SAED patterns are consistent with the XRD
Fig.

## 4. X-ray

results shown in Fig. 4. An EDS line scan, performed on the nano-
b diffraction patterns
s obtained on the Nb15Ta10W75 and
(Nb15Ta10W75)98.5C1.5.
precipitates inside the grains (red dashed box), is shown in Fig. 6(c).
The C and Nb contents are the highest in the center of the nano-scale
of the grains oriented along the Z-axis direction. This is due to the sig-
precipitate, while other elements are significantly lower. Especially,
the W content is significantly lower in the precipitate than in the matrix,
nificant temperature gradient along the Z-axis, which leads to the for-
whereas Ta content is nearly constant. The elemental distribution con-
mation of columnar grains aligned with it [39].
firms that the observed particles are indeed NbC nano-precipitates, with
To further identify the grain morphology, the grain shape aspect
the length and width of about 67 ± 5 and 45 ± 4 nm, respectively.
ratio (GSAR) is analyzed, as shown in Figs.5 (c1-c4). The GSAR is defined
as the ratio of the short to long axis of the grains, with distinct colors
Fig.6(d) displays the TEM dark-field (DF) micrographs of the NbC
used to differentiate grain morphologies. Both Nb15Ta10W75 and
precipitates within (Nb15Ta10W75)98.5C1.5, which is obtained along the
(Nb15Ta10W75)98.5C1.5 exhibit cellular grain morphology on the X-Y
[222]nbc zone axis (Fig. 6(e)). The results show that a considerable
plane. The GSAR values are closely concentrated in the range of 0.30.6,
number of precipitates are uniformly distributed in the alloy. Based on
% for Nb15Ta10W75 and 63.5 % for
the DF-TEM images, the average diameter (r) of these precipitates
comprising
66.3
(Nb15Ta10W75)98.5C1.5, as shown in Figs.5 (c1) and (c3). The GSAR of
(measured using the Image-Pro-Plus software) is determined to be 37.2
(Nb15Ta10W75)98.5C1.5 on the X-Z plane increases significantly compared
± 4.3 nm (Fig. 6(f). Their number density (N) was estimated by using
to that of Nb15Ta10W75, particularly in the range of 0.30.6, rising from
the following equations [40]:

## 35.5. % to 71.0 %, as shown in Figs.5 (c2) and (c4). This indicates a

significant increase in short axis grains, and the addition of WC powders
f
N =
effectively inhibits the growth of columnar grains. Besides, GSAR maps
(5)
4/3πr3
over a larger area (500 µm × 600 µm) on the X-Z plane were obtained to
∑ i2Tavg
further distinguish grain morphology (Figs.5 (d1-d2)). The results indi-
f =
2xpyptd
(6)
cate that (Nb15Ta10W75)98.5C1.5 has a higher GSAR value, with a high
proportion of 69.9 % at 0.30.6 and 8.7 % at 0.61.0, indicating the WC
powder addition suppresses the columnar grain growth and results in an
Tavg = 1.15R(1) + 2.07R(2) + 2.99R(3) + 3.91R(4)
(7)
equiaxed microstructure.
where f is the volume fraction. Tavg is the average thickness of NbC,
Except for grain morphology, the pole figures (PFs) also confirm that
taken across four different locations (R(i)) of the TEM sample [40], xp
the addition of WC powders suppresses the columnar grain growth, as
shown in Figs.5 (e1-e4). In the X-Y plane, random texture is noted for
and yp are the dimensions of the TEM image, and td is the thickness of the
both the alloys (Fig. 5(e1) and (e3)). The maximum uniform distribution
TEM sample. The obtained N value of the NbC precipitate, 9.7 ± 3.8 X
(MUD)
values
2.93
and 2.83 for Nb15Ta10W75 and
are
(Nb15Ta10W75)98.5C1.5, respectively. In the X-Z plane of Nb15Ta10W75,
formly dispersed in (Nb15Ta10W75)98.5C1.5 RMPEAs.
strong {100} texture can be observed (Fig. 5(e2)), which is the preferred
For Nb15Ta10W75, the typical atomic structure of the matrix is
grain growth direction during LPBF [10,11]. The corresponding MUD
observed from the intragranular region using HRTEM (Fig. 7(a)). The
value is 3.29. With the WC powder addition, significant reduction in the
HRTEM image of this region is enlarged, and the corresponding Fast
intensity of {100} texture is noted, making the texture random (Fig. 5
Fourier transform (FFT) images are shown in Figs.7 (b1) and (b2),

diffraction spots are observed at the NbC/matrix interface (Fig. 7(e2)),
where αNbc and αBcc are the lattice parameters of the carbide and BCC
matrix (Fig. 7(d2)) and NbC (Fig. 7(f2)). In contrast, two sets of
αNbC
(f1-f2), respectively. Only one set of diffraction spots is present in the
(8)
=
αNb - αC
patterns of the nano-precipitates are shown in Figs.7 (d1-d2), (e1-e2), and
following equation [42]:
(Nb15Ta10W75)98.5C1.5. High-magnification HRTEM images and FFT
the BCC matrix and NbC nano-precipitates was estimated using the
crystal structures of the matrix, NbC/matrix interface, and NbC in
lattice parameters of 3.26 and 3.36 Å. The lattice mismatch (δ) between
which corresponds to a lattice parameter of 3.22 Å. Fig. 7(c) shows the
(Fig. 7(d1)) and 0.231 nm (Fig. 7(f1)), respectively, with corresponding
The interplanar spacing along [011]Bcc was measured as 0.22 nm,
measured interplanar spacings of [011]Bcc and [011]Nbc are 0.224 nm
tional diffraction spots, consistent with the results of SAED (Fig. 6(b1)).
The
confirming the phase relationship of [011]Bcc//[0-1-1]Nbc.
respectively. The selected area exhibits a BCC structure without addi-
Pole figures showing the variations in the texture.
.0
Max=3.02
Max=3.29
MUD
{OO1
TL
OO1
(e4)
(e2)
M
Max=2.83
Max=2.93
YOO
(l)
Z
0.6-1.0: 8.7 %
0.6-1.0: 1.3 %
%
□0.3-0.6:69.9
0.3-0.6:41.3 %
%
0.0-0.3:21.4
0.0-0.3:57.4 %
axis
Short/long
Short/long axis
(p)
GSAR
*
V
(0>.91)
wn

## 40. μm

a0
un
HAGB
0.6-1.0: 5.8 %
0.6-1.0: 8.8 %

## 1.3. %

0.6-1.0:
0.6-1.0: 5.7 %
0.3-0.6:63.5 %
0.3-0.6:35.5 %
□0.3-0.6:71.0 %
0.3-0.6:66.3 %
0.0-0.3:23.2 %
0.0-0.3:27.7 %
0.0-0.3:63.2 %
0.0-0.3:28.0 %
Short/long axis
axis
Short/long
Short/long axis
HD
un
wn

## 40. μm

un
IOL
ajom
unot
Z
umot
anon
IPF
(tq)
q)
(Lq)
wn
OS
wn
wn
X
Poors
Z
A
Poors
Z
Pooes
X
SEM
(B)
(EB)
(2D)
(B)
(Nb15Ta10W75)98.5C1.5
Nb15Ta10W75

(Nb15Ta10W75)98.5C1.5
(b2)
.Z.A. [131]Bcc
(a1)
Nb15Ta10W75
(b1)
Z.A. [011IBcc
(a2)
200:
-
-
-
AO
-
Grain boundary
Grain boundary
I
-
I
-
Precipitations
-
I
-
nm
-
(c)
Nb
Matrix
NbC
precipitation
Matrix
Ta

## 60. ±2.1

%
C

## 22. ±1.5 %

Liner scanning
Position (nm)
(d)
Z.A.[1-10]Bcc
(002)
(222)
(f)
r : 37.2 ± 4.3 nm
(e)
Frequency
NbC
m
(222)
(002)
[110]Bcc//[110]Nbc
nm
Particle Size
(nm)
SAED patterns. (c) EDS line scans showing the compositional distribution inside the nano-precipitates. (d) A TEM dark-field image of (Nb15Ta10W75)98.5C1.5 con-
taining NbC precipitates and (e) the corresponding SAED pattern. (f) Normal distribution pattern of NbC precipitates.
exhibits a mixture of cleavage and quasi-cleavage fracture characteris-
phases. The lattice mismatch between the BCC matrix and NbC is esti-
tics (Fig. 8(b3)). After adding WC powder, the fracture mechanism
mated to be 2.9 % (<5 % [28,41,42]), indicating that the interface be-
across both compression directions transitions to quasi-cleavage frac-
tween NbC and the matrix is coherent (Fig. 7(e1)).
ture, exhibiting a greater number of torn edges (Figs.8 (b2) and (b4)).
The
of
Nb15Ta10W75
and
stress-strain
responses
(Nb15Ta10W75)98.5C1.5, with the compression direction perpendicular to

## 3.3. Mechanical properties

BD, at HT are shown in Figs.8 (c1-c4). At 1000, 1200, and 1400 °C, the
stress-strain curves for Nb15Ta10W75 and (Nb15Ta10W75)98.5C1.5 exhibit
Representative compressive engineering stressstrain responses and
elastic deformation before fracture, with some limited plasticity only
fracture morphologies are shown inFig. 8. The mechanical properties at
observed at 1600 C. This is probably due to the transition from cross-
different temperatures are listed in Table 1. Nb15Ta10W75 displays sig-
kinking to a diffusion-controlled dislocation slip mechanism at higher
nificant mechanical anisotropy, as seen from Figs. 8(a1) and (a2). The
temperatures, facilitating dislocation slip and hence plastic deformation
compressive yield strength (σo.2), ultimate compressive strength (om),
[43]. More importantly, σ0.2 of (Nb15Ta10W75)98.5C1.5 0ver the temper-
and fracture strain (ε) at RT and parallel to BD are 759 ± 17 MPa, 939 ±
ature range of 1000 and 1600 °C exceed those of Nb15Ta10W75 by about

## 16. MPa, and 2.6 ± 0.2 %, respectively. Perpendicular to BD, they are

## 100. MPa. The mechanical test results indicate that the incorporation of

## 1409. ± 22 MPa, 1520 ± 13 MPa, and 5.3 ± 0.3 %, respectively. The σ0.2

WC powder into Nb15Ta10W75 can eliminate anisotropy, improve RT
and ε values in the direction perpendicular to BD are nearly-double of
plasticity, and enhance strength at both RT and HT.
those along BD, illustrating significant anisotropy. In contrast, incor-
porating WC powder into Nb15Ta10W75 effectively eliminates the me-

## 4. Discussion

chanical anisotropy due to CET (Fig. 5). In addition, σ0.2, σm, and ε along
BD increased significantly to 1591 ± 25 MPa, 1667 ± 13 MPa, and 7.4 ±

## 4.1. Formation mechanisms of the NbC precipitates

## 0.1. %, respectively. Perpendicular to BD, they increased to 1615 ± 28

MPa, 1692 ± 21 MPa, and 8.3 ± 0.4 %, respectively. Note that σ0.2 and ε
From Fig. 6, it is obvious that the WC particles added to the RMPEA
of (Nb15Ta10W75)98.5C1.5 in the two orientations are nearly the same.
powder completely dissolves during the LPBF process, and then lead to
The fractographs obtained from the specimens tested in different
the formation of the NbC nano-precipitates within the matrix. These
orientations are shown in Figs.8 (b1-b4). For Nb15Ta10W75, fractographs
precipitates suppress the columnar grain growth, and, in turn, reduce
of specimens tested along BD show cleavage fracture characteristics,
the mechanical anisotropy (Figs. 5 and 8). It is well known that in-situ
with relatively smooth surfaces and river patterns (Fig. 8(b1)). When
compressed in the direction perpendicular to BD, the fractured surface

Matertalia 297 (2025) 121325
Nb15Ta10W75
(Nb15Ta10W75)98.5C1.5
b
NbC
e
d
BCC
Interface
nm
BCC
nm
NbC
(f1)
NbC
552532353:
Interface
(011)
Coherent
interface
(011)
nm
BCC
BCC
nm
BCC
nm
H(d2)
(e2)
Z.A. [011]BC
(f2)
21i
Z.A. [011]BCC
nm-1
Z.A. [011]Nbc
nm
Z.A. [011]BCc
Fig. 7. (a) HRTEM image, (b1) an enlarged HRTEM image, and (b2) the corresponding FFT pattern obtained on Nb15Ta10W75. (c) HRTEM image of the interface
between BCC matrix and NbC precipitate in (Nb15Ta10W75)98.5C1.5. Magnified HRTEM images and corresponding FFT patterns used to analyze the crystal structure at
different locations of (d1-d2) the BCC matrix, (e1-e2) the NbC/matrix interface, and (f1-f2) the NbC precipitates.
precipitation during LPBF facilitates CET [44]. Therefore, the mecha-
-QD
(9)
nisms responsible for the NbC formation in (Nb15Ta10W75)98.5C1.5 need
S = Soexp
RT
elucidation, which is attempted in the following through a comparative
analysis of the physical characteristics and precipitation kinetics.
where So is the intrinsic diffusion coefficient (m2/s) and Qp is the acti-
Generally, a lower mixing enthalpy (∆Hmix) indicates a stronger af-
vation energy for diffusion (kJ/mol). These parameters are obtained
finity between the elements, which favors the formation of stable
from literature through experiments or simulations of refractory metals
compounds during LPBF [45]. The values of ΔHmix of Nb, Ta, and W with
composed of Nb, Ta, and W [49], and listed in Table 2. The
C are shown in Fig. 9(a). Amongst them, Nb-C exhibits the lowest ΔHmix,
temperature-dependence of ç for Nb, Ta, W, and C is shown in Fig. 9(d).
compared to Ta-C and W-C, suggesting a strong preference for forming
The results indicate that C has significantly higher than the metallic
NbC. This observation rationalizes their in-situ formation during LPBF of
elements across different temperatures, which would also facilitate the
(Nb15Ta10W75)98.5C1.5. Notably, the comparison of ΔHmix values among
in-situ formation of carbides including NbC. Overall, the small ΔHmix as
metallic compounds provides a meaningful starting point for the kinetic
well as large ΔG*, Nv, S of NbC, are possibly the reasons that ensure the
calculations (including precipitate nucleation and growth), ensuring
nucleation and growth of NbC during LPBF.
that the predicted phase was the most thermodynamically favorable
Variations in the phase volume fractions and element contents under
one, while ruling out metastable phases (for example, ∆Hmix for W-C is
the conditions of non-equilibrium solidification (107 K/s) are analyzed
—60 kJ/mol). The nucleation of precipitates is predominantly influ-
to further explore the origin of in-situ formed NbC. The non-equilibrium
enced by the thermodynamic driving force (∆G*), which influences the
cooling path containing NbC is shown in Fig. 10(a), which is derived
nucleation rate (Ny) [46,47]. Using the Thermo-Calc software, values for
from stage 2 of the non-equilibrium cooling curve depicted in Fig. 1(d2).
∆G* and Ny of the BCC and NbC phases that are included in the
The variations in the volume fractions of the liquid, BCC and NbC phases
non-equilibrium solidification curve 2 of Fig. 1(d2) are obtained. Results
with the temperature are shown in Fig. 10(b). As the temperature de-
are shown in Figs.9 (b-c). The maximum ∆G* value of NbC (6177 J) is
creases from 2755 to 2680 °C at a cooling rate of 107 K/s, the liquid
nearly-seven times that of the BCC phase (851 J), resulting in Ny for NbC
phase simultaneously transforms into BCC and NbC phases. Within this
being about 107 times higher than that for BCC phase. On this basis, it is
temperature range, the formation temperature of NbC (2740 °C) slightly
reasonable to assume that NbC nucleates rapidly (even at high cooling
lags behind that of the BCC phase (2753 C), with higher ΔG*, Ny, and ζ
rates (107 K/s) that prevail during LPBF).
values promoting the transformation. The phase transformation path-
The diffusion coefficient (ç) also plays a critical role in the nucleation
ways are governed by elemental redistribution. Therefore, the Ther-
and growth of NbC [48]. The ζ values of Nb, Ta, W, and C are estimated
moCalc software was employed to calculate the compositional
using the following equation [49]:
variations under non-equilibrium cooling conditions (107 K/s). Results,
shown in Figs.10 (c1-c4), indicate that, during the formation of NbC, C

(a1)
(Nb15Ta10W75)98.5C1.5
RT
(a2)
(Nb15Ta10W75)98.5C1.5
RT
Nb15Ta10W75
Nb15Ta10W75
Z
(BD)
Xx
X
Strain
(%)
Strain (%)
:(b
I/BD
Fb3)
//BD
:(b2)
⊥BD
(b4)
⊥BD
Fracture morphology
Cleavage fracture
→
Quasi-cleavage
S
fracture
Quasi-cleavage
fracture
nm
nm
nm
(c1)
(c3)
•C
Engineering stress (MPa)
Z
*
Y
X
Strain (%)
Nb15Ta10W75
(Nb15Ta10W75)98.5C1.5
vertical samples and (b3-b4) horizontal samples; HT stress-strain curves at (c1) 1000, (c2) 1200, (c3) 1400, and (c4) 1600 C.
Table 1
Mechanical properties of Nb15Ta10W75 and (Nb15Ta10W75)98.5C1.5 along different compression directions.
Nb15Ta10W75
(Nb15Ta10W75)98.5C1.5
(MPa)
ε ( %)

## 0.2. (MPa)

m (MPa)
ε ( %)
σ0.2 (MPa)
Parallel-BD

## 759. ± 17

## 939. ± 16

## 2.6. ± 0.2

## 1591. ± 25

## 1667. ± 13

## 7.4. ± 0.1

Perpendicular-BD

## 1409. ± 22

## 1520. ± 13

## 5.3. ± 0.3

## 1615. ± 28

## 1692. ± 21

## 8.3. ± 0.4

## 1009. ± 10

## 1451. ± 13

## 15.9. ± 0.5

## 1105. ± 31

## 1602. ± 15

## 16.4. ± 0.1

## 942. ± 27

## 1372. ± 21

## 17.2. ± 0.4

## 1042. ± 29

## 1513. ± 22

## 15.0. ± 0.2

## 841. ± 25

## 1242. ± 24

## 14.4. ± 0.1

## 952. ± 20

## 1397. ± 24

## 14.8. ± 0.8

## 640. ± 18

## 744. ± 9

## 14.6. ± 0.5

## 750. ± 16

## 957. ± 12

## 15.3. ± 0.7

and Nb rapidly diffuse to it in the liquid phase, reaching 18.5 and 68.5
experiments were performed to determine the composition of the NbC
at. %, respectively. On the other hand, W segregates to the BCC phase,
nano-precipitates, after preparing the samples by FIB and identifying the
reaching 78.4 %. Ta is relatively uniformly distributed in both the
precipitate locations using TEM (Fig. 10(d)). Results indicate significant
phases, with concentrations of 15.9 and 8.5 at. %, respectively. The
aggregation of C and Nb in NbC, while W is absent (Figs.10 (e1-e4)). To
combination of (i) rapid cooling process of LPBF [13], (ii) the low
identify NbC and quantify the elemental distributions, a surface with a C
diffusion rate of refractory metals (Fig. 9(d)), and (ii) the minimal
concentration of 0.15 at. % is constructed (Fig. 10(f)), and a one-
variation in elemental composition during non-equilibrium solidifica-
dimensional (1D) composition map perpendicular to this surface is
tion (Fig. 10 (c1-c4)), result in the preservation of precipitate composi-
created (Fig. 10(g)). The elemental content in NbC obtained from APT is
tions that essentially mirrors the initial solidification composition of
consistent with the Thermo-Calc predictions (Fig. 10(h)), which con-
liquid pools. Therefore, measurement of the composition of NbC pre-
firms the accuracy of non-equilibrium solidification calculations, indi-
cipitate and comparing it with the composition calculated by
cating that NbC originates from the liquid phase. As the temperature
Thermo-Calc can effectively confirm the source of the precipitate.
reaches the precipitation range for NbC (2680 to 2755 °C), the combi-
For verifying the Thermo-Calc results experimentally, APT
nation of low ΔHmix and high ∆G*, Ny, S values promotes Nb and C atoms

(aFormation enthalpies
(b) Nucleation driving force
(c)
Nucleation rate
-120
T2
10^26
T1
10^19
-102
BCC
Enthalpy (kJ/mol)
-101
For verifying the Thermo-Calc results experimentally, APT
1.2
NbC
1.8
Nucleation rate (m
T2
Driving force
0.8
tion (Fig. 10 (c1-c4)), result in the preservation of precipitate composi-
phases, with concentrations of 15.9 and 8.5 at. %, respectively. The
0.6
0.4
cipitate and comparing it with the composition calculated by
T1
dimensional (1D) composition map perpendicular to this surface is
0.0
awwgrgrggggegeeeeGGe
o
Nb-C
Ta-C
W-C
Temperature (C)
Temperature (°C)
Diffusion coefficients

## 600. (K)

Nb
Ta
W
C
B
-40
) o
-80
-120
10/T (K)
Table 2
method (for the averaged size of columnar grains), the impact of WC
Intrinsic diffusion coefficients and activation energies for diffusion.
particles on the size of the columnar grains could be revealed. The grain
size on X-Z plane decrease from 7.34 ± 1.3 µm in Nb15Ta10W75 to 6.10 ±
Nb
Ta
W
C
Ref.

## 0.9. µm in (Nb15Ta10W75)98.5C1.5, as shown in Fig. 11(b) (similar trend

So (10-4 m{2/s)
4.5
6.2
2.58
[49]
can be seen for the X-Y plane as well, as shown in Supplementary-Note
QD (KJ/mol)
480.2
601.7
666.2
140.6
[49]
4). Figs.11(c) and (d) show the grain size distributions with the mea-
surement line directions oriented perpendicular or parallel to the Z-axis,
to rapidly aggregate resulting in the nucleation of NbC from the liquid
respectively. The vertical grain size (10.4 µm) in Nb15Ta10W75 exceeds
phase. During LPBF, the added WC particles dissolve into the molten
the horizontal one (6.72 pm), typical of columnar grain morphology.
pool first, followed by the distribution of C throughout the liquid alloy,
The grain size in (Nb15Ta10W75)98.5C1.5 decreases to 6.46 µm in the
and subsequent precipitation of NbC from the liquid phase upon solid-
horizontal direction and 5.98 um in the vertical direction, displaying a
ification. This process circumvents the uneven distribution and
much more equiaxed morphology than in Nb15Ta10W75. These results
agglomeration of secondary particles, which is a common phenomenon
further confirm that the NbC precipitates not only inhibit the columnar
otherwise [50].
grain growth during LPBF, but also lead to the refinement of the grains.
The influence of NbC and corresponding process parameters on the
suppression of columnar grains is analyzed using the inter-dependence

## 4.2. Effect of the NbC precipitates on the grain structure

model, which effectively evaluates the synergetic effect of alloy
composition, nucleation efficiency, and interparticle distance on grain
To analyze the effects of the in-situ formed NbC on the grain shape,
refinement [52,53]. This model has been widely used to evaluate grain
especially on the planes along BD (X-Z and Y-Z), the grain boundary
size in alloys produced using casting [54], welding [55], and additive
distributions are obtained and plotted in Figs.11 (a1-a4). Based on these
manufacturing [56]. The interdependence model and the key control
images, the size of the irregular grains is measured using two different
parameters of grain size can be expressed as following [57]:
(line intercept and area measurement) methods. The line intercept
d = Xcs + Xl + Xsd
method measures the average size of grains intersected by a line, while
(12)
the area measurement method estimates the average grain size based on
D.zΔTn
the grain's area. The equations for these methods are the following [51]:
Xcs =
(13)
vQ
$\racg}$
dLine=
CE_or2}$
di
(10)
Ng
∆Tn =
i=1
ΔSy
(14)
Ng
Ai
(Ai/π)
1/2
dArea
n
(11)
Q = ∑i( − 1)·,i
identify NbC and quantify the elemental distributions, a surface with a C
Ai
(15)
=1
i=1
where dLine is the average grain size obtained by the line intercept
XαQ
method, Ng is the total number of grains, d is the length for grain i, dArea
(16)
is the average grain size obtained by the area method, Ai is the area of
∆T
grain i, and 2(A/π)1/2 is the equivalent diameter based on the area of
Xsdα
∆Tn
(17)
grain i. By comparing grain size values obtained by the line intercept
method along the X direction (for the width of columnar grains), along
∆T = ∆T + ∆Tt
the Z direction (for the length of columnar grains), and by the area
(18)

b
of 1.5%;
Liquid
Carbon
addition
←→
BCC + NbC
(°C)
Liquid
Phase
BCC
Phase
NbC Phase
Phase-transition predicted by Thermocalc
Temperature
Temperature
e
00oo0ooo
Mole fraction of solid (%)
Mole fraction
of solid
(%)
(c1)
(c2)
Nb
(c3)
Ta
(c4)
C
W
80∞
In Liquid
r
In BCC
In BCC:
In BCC
oopom
HO0O.
In NbC

## 0.0. %

18.5
%

## 14.5. %

68.5
8.5
%
15.9
%

## 0.0. %

78.4
%
C content (at.%)
Nb content
at.%)
Ta content (at.
W content (at.%)
%
(e1)
(d)
(e3)
(e4)
NbC
Element distribution of NbC precipitates
Enriched
Depleted
C (2.1
at.%)
Nb
(14.2
at.%)
Ta (9.3at.%)
W
(76.7 at.%
(f)
(g)90
Nb(at.%)
Ta(at.%)
W(at.%)
C(at.%)
APT-NbC
(NbC)
(Grain)
%0
Interface
67.3
74.7
67.3
17.2
Molar conter
15.3
Concentration
0.0
17.2
13.1
0.0
15.3
18.5
15.9
10.5
0f
68.5
0.1
0.2
Thermocalc-NbC
C
Nb
Ta
W
C-0.15 at.% surfaces
Distance (nm)
ig. 10. (a to c) Predictions and (d to f) experimental verification. (a) Non-equilibrium cooling path containing NbC nano-precipitates. (b) Variations of the volume
ractions of different phases with temperature. (c1-c4) Element distribution in different phases. (d) An image of the APT samples containing a NbC precipitate. (e1-e4)
Distribution maps of Nb, Ta, W, and C near and inside NbC. (f) Equal concentration C surface of 0.15 at. % distinguishing the NbC precipitate. (g) 1D concentration
calculations.
are the partition coefficient and solute concentration, respectively. Xdl is
(19)
∆TcαQ
the diffusion field distance of accumulated solutes that can compensate
(20)
for insufficient ΔTcs due to solute diffusion at the S/L interface and is
∆TtαVa
directly related to Q values. Xsd is the average distance from Xdl to the
(21)
nearest particle that can effectively nucleate. It is closely related to the
Va = vcosφ
effective nucleation particle density and can be evaluated through
undercooling. When ΔTn is lower than the undercooling at the solid/-
where dgs is the grain size predicted using the interdependence model,
liquid interface (∆T), numerous heterogeneous nucleation events are
Xcs is the critical distance that grains must grow before producing
activated, reducing Xsd and inhibiting columnar grain formation [58].
adequate ΔTcs to initiate subsequent nuclei, D is the diffusion coefficient
Xsd is positively correlated with ΔT and negatively correlated with ΔTn.
of the solute in the liquid, z is the fraction of ΔTcs required for hetero-
ΔT is composed of ∆Tcs and thermal undercooling (∆Tt) under
geneous nucleation, v is the laser scanning speed, ΔTcs is the under-
non-equilibrium solidification conditions [58]. ΔTcs is primarily associ-
cooling of critical nucleation, CE is the elasticity coefficient, ΔSv is the
ated with the solute segregation occurring ahead of the solid/liquid
entropy of fusion per unit volume, and δ is the degree of interfacial
interface and can be quantitatively evaluated using Q [25]. ΔTt is the
lattice parameter match between the nucleating particles and the ma-
thermal undercooling when the actual growth rate (Va) at the solid/-
trix. ΔTn is closely related to δ between nucleating particles and matrix.
liquid interface lags behind the theoretical pull rate (Vtheo) induced by
A smaller δ lowers ΔTn is required for the activation of heterogeneous
the high cooling rate that prevails during LPBF [58]. Generally, Va is
nucleation processes, i.e., ∆Tn α δ [52]. Q is a growth restriction factor;
directly correlated with laser scanning speed v [53]. φ is the angle (°)
mi is the slope of the liquidus line for the th solute in the alloy; k and Co,i

. Daan et al.
Nb15Ta10W75
(Nb15Ta10W75)98.5C1.5
LAGB:48.9 %
(a2)
LAGB:37.2
LAGB:56.7
%
LAGB:68.7 %
(2 ≤θ <15
(2° ≤ 0 <15
(2° ≤ θ <15°
HAGB:51.1
%
HAGB:62.8 %
HAGB:43.3 %
HAGB:31.3 %
(15°<0 )
(15<θ
(15° <0
(15°<0 )

## 40. μm

(b)
Grain Size (Area)
(c)
Grain Size (Horizontal)
(d)
Grain
Size (Vertical)
0.3
Fraction
d=7.34 μm
=0.2
d=6.72 μm
0.2
Fraction
d=10.4
μm
0.0
X-Z
0.0
0.3
d=6.10 μm
d=5.98 μm
E0.2
d=6.4 6µm
0.2
Grain Size (μm)
Z
Y
X
Y
X
Y
X
Nb15Ta10W75
(Nb15Ta10W75)98.5C1.5
between the Va and v directions. The degree of ΔTt is controlled by the
values of v. As the value of v increases, the delay between Va and Vtheo
Table 3
becomes more pronounced, resulting in a larger ΔTt.
Growth restriction factors and related calculation parameters for i th solutes.
The comparative evaluation of the solidification distance and
m
k
Q
Ref.
undercooling illustrates the inhibitory effect of adding WC to RHEA and
Nb
3.4
1.08
0.27
[17]
the resulting NbC precipitates on the columnar grains, as shown in
Ta
16.5
1.48
8.0
[17]
Fig. 12. The incorporation of WC and the presence of NbC reduces Xcs for
W
15.1
2.50
22.7
[17]
three reasons. First, NbC being coherent with the matrix (Fig. 7(e1))
C
-55
→0
[17]
Nb15Ta10W75
/
reduces ΔTn and shorten Xcs. Second, WC powder markedly improves the
17.82
This work
(Nb15Ta10W75)98.5C1.5
/
18.38
This work
laser absorptivity (Fig. 2(d2)) and increases v (Section 3.1), resulting in
the shortening of Xcs. Third, C that is released through the dissolution of
WC increases Q of (Nb15Ta10W75)98.5C1.5 (Table 3), further reducing Xcs.
than that of Nb15Ta10W75 due to higher Q. The presence of NbC also
Therefore, (Nb15Ta10W75)98.5C1.5 exhibits a smaller Xcs compared to
reduces Xsd. The coherency between NbC and the matrix also helps
Nb15Ta10W75. The Xdl term of (Nb15Ta10W75)98.5C1.5 is slightly smaller
reduce ΔTn required for heterogeneous nucleation. In Nb15Ta10W75,
(a)
GAM
ΔT < ΔTn
(b)
GAM
ΔT≥ ΔTn
TL
No nucleant
Nucleation
Tn
ΔTn
Tcs
T
AT
..TS
Ts
∆T
AT
Tt
In situ NbC
BD
Native nucleant
BD
precipitation
Xcs
Xdl
Xsd
Xcs
Xal
Xsd
In
situ formed NbC
precipitation
O
Without external WC powder addition
Adding external WC powder addition
Fig. 12. Schematic illustrations of the generation of the undercooling including ΔT, ∆Tc ΔTt and the solidification distance including Xcs, Xdl Xsd in (a) Nb15Ta10W75
and (b) (Nb15Ta10W75)98.5C1.5, illustrating the inhibitory effect of adding WC powder and optimizing process parameters on columnar grains. The schematic
llustration is not drawn to scale and is intended for illustrative purposes; actual undercooling and solidification distances may have deviations.

heterogeneous nucleation primarily occurs on the native nuclei parti-
1/2
cles, such as impurities or oxides that may be present in the melt pool.
constituent pure metals [64], k is the Hall-Petch slope (210 MPa·µm
for refractory metals [64]), d is the average grain size (estimated using
Such nuclei are usually incoherent with the matrix, characterized by
the area method on the EBSD data obtained on the X-Z plane (Fig. 11
relatively high δ, leading to larger ΔTn [52]. Besides, the incorporation
(b)), M is the Taylor factor (~2.733 for BCC refractory metals) [64], α is
of the WC powders into Nb15Ta10W75 increases ΔTcs owing to the pres-
an empirically determined constant (0.5 for BCC metals [64]), µ is the
ence of C in solution, which has a high Q value (Table 3). Simulta-
shear modulus calculated according to the mixed weighting equation
neously, the added WC powder significantly enhances the laser
[29], and ρ is obtained from the XRD analysis (Fig. 4). Since dislocations
absorptivity in (Nb15Ta10W75)98.5C1.5, thereby increasing v (Section 3.1)
cannot cut through the NbC particles because of their large size (>37
and ultimately increasing the degree of ΔTt. The incorporation of WC
nm) [63], the Orowan looping mechanism is the primary
and the presence of in-situ NbC nano-precipitates reduce ΔTn while in-
precipitation-strengthening mechanism [63], which was used to esti-
crease ΔT, meeting the nucleation condition of ΔT ≥ ΔTn, which, in turn,
mate Δσp for (Nb15Ta10W75)98.5C1.5. Due to the rapid cooling rates and
shortens Xsd for (Nb15Ta10W75)98.5C1.5. In conclusion, the above theo-
the small melt pool sizes associated with the LPBF process, it is difficult
retical analysis made on the basis of the interdependence model in-
for solutes and solute atoms to rapidly diffuse and generate concentra-
dicates that adding WC powder and the in-situ NbC formation reduces
tion gradient over a larger length scale (of micrometer level) [13]' [65].
Xcs, Xdl, and Xsd, which effectively inhibit the columnar grain growth in
The Toda-Caraballo model can evaluate the solid-solution hardening
(Nb15Ta10W75)98.5C1.5. Moreover, driven by the combination of low
effect of RMPEAs fabricated using the LPBF process [66]. This model
ΔHmix and high ΔG*, Nv, values, NbC particles re-precipitate from the
overcomes the difficulty of distinguishing "solute-solvent" in the high
liquid phase and are uniformly distributed, which serve as heteroge-
entropy alloys, and utilizes a matrix to calculate lattice distortion caused
neous nucleation sites and pin grain boundaries (preventing grain
by a small amount of component fluctuations, which is consistent with
coarsening) during repeated heating that solidified layers undergo
the atomic diffusion behavior under non-equilibrium conditions. AoSSH
during LPBF [52].
assumed to be the same
for
Nb15Ta10W75 and
was
(Nb15Ta10W75)98.5C1.5, as all the added C precipitates out in the form of
NbC.

## 4.3. Effect of NbC on the mechanical properties at room temperature

The contributions of the different strengthening mechanisms to
Nb15Ta10W75 and (Nb15Ta10W75)98.5C1.5 at RT are shown in Fig. 13.
The anisotropy of the mechanical properties at RT is mainly
Their sum, being close to oy obtained from the experiment, renders
controlled by grain morphology [15]. Both as-fabricated Nb15Ta10W75
reasonable validity to the methods employed for the estimation. Δσo and
and (Nb15Ta10W75)98.5C1.5 exhibit a high relative density of above 99.2
ΔossH are the primary contributors to the strength of Nb15Ta10W75,
% (Fig. 3), which minimizes the potential influence of porosity on me-
providing 430 and 337 MPa respectively, which correspond to 32.9 %
chanical properties and anisotropy [60,61]. The formation of NbC
and 25.8 % of oy [64], respectively. 6 of Nb, Ta, and W are 240, 189, and
nano-precipitates in the (Nb15Ta10W75)98.5C1.5 effectively reduces

## 550. MPa, respectively. The high proportion of W content in

anisotropy. During the manufacturing of Nb15Ta10W75 using the LPBF
Nb15Ta10W75 significantly enhances Δσ0, contributing substantially to
technique, the presence of a steep thermal gradient promotes grain
σy.
The severe lattice distortion significantly improves ΔσssH [29],
growth towards the melt pool core [16], ultimately forming a micro-
thereby positively contributing to σy.
structure with columnar grains that are parallel to the Z-axis (Figs.5 (c2)
In (Nb15Ta10W75)98.5C1.5, both ∆σ0 and ΔσssH continue to be the
and (d1)). When the alloy is stressed along the Z-axis, they align with the
major strengthening contributors, accounting for 28.3 % and 22.2 % of
long axis of the columnar grains (Figs.5 (c2) and (d1)). The straight
σy, respectively. The strengthening effect of these mechanisms does not
boundaries of the columnar grains along their long axis promote crack
vary because of negligible variations in the matrix composition. How-
propagation during plastic deformation [59], resulting in poor
the
NbC
precipitates generated during
LPBF
of
ever,
compressibility and strength of 2.6 % and 759 MPa, respectively. In
(Nb15Ta10W75)98.5C1.5 can pin GBs (from coarsening during the thermal
contrast, forces applied along the X-axis are parallel to the short axis of
cycles of LPBF) and dislocations, thereby refining grains (Fig. 11) and
the columnar grains (Figs.5 (c2) and (d1)). Compared to long-axis
increasing ρ (Fig. 4). Benefiting from these microstructural modifica-
columnar GBs, short-axis curved boundaries effectively hinder crack
tions, ∆σGB and ∆opis increase to 269 and 313 MPa, respectively.
propagation [59], enhancing compressibility (5.3 %) and strength (1409
Moreover, the NbC precipitates themselves can also enhance the
MPa). The incorporation of WC powder into Nb15Ta10W75 induces the
strength by hindering the dislocation mobility, contributing an addi-
NbC precipitates (Fig. 7) and changes the grain morphology to an
tional 167 MPa. Thus, the enhanced strength of (Nb15Ta10W75)98.5C1.5
equiaxed one (Figs.5 (c4) and (d2)). As a result, the mechanical anisot-
mainly arises from the combination of ΔσGB, ΔσpIs, and ∆σp.
ropy is reduced substantially. In addition, NbC enhances the RT me-
Furthermore, (Nb15Ta10W75)98.5C1.5 exhibits superior plasticity (8.3
chanical properties. For Nb15Ta10W75 and (Nb15Ta10W75)98.5C1.5, the
%) compared to Nb15Ta10W75 (5.3 %), despite comparable dislocation
contributions from solid-solution hardening (∆ossH), grain boundary
densities in them (Section 3.2). The higher plasticity is also reflected in
strengthening (∆σGB), dislocation strengthening (∆opis), and precipita-
the fracture morphologies (Figs.8 (b3b4)). This difference in the plastic
tion strengthening (∆σp) to the total yield strength (oy) can be estimated
deformability between the two alloys examined is mainly due to the
using the following relations [6264]:
differences in microstructure. Specifically, (Nb15Ta10W75)98.5C1.5 con-
tains a higher population of LAGBs than Nb15Ta10W75 (Figs.11(a2) and
σy = Δσ + ∆σsH + ∆σGB + ΔσDI + ∆p
(22)
(a4)), which is caused by the pinning effect of precipitates on grain
boundaries (Fig. 6). The high proportion of LAGBs can blunt the crack
∆σ = ∑
(23)
tips and hinder crack propagation [59], and bear a larger degree of
deformation before fracture by homogenizing the strain [60], ultimately
∆σGB = K−1/2
(24)
improving plasticity and transforming fracture mechanism from partial
cleavage to quasi-cleavage.
∆σD = Mαµbρ1/2
(25)

## 4.4. Effect of the nano-precipitates on HT mechanical properties

μb
f1/21
∆σp = 0.26
(26)
b
r
Fig.14(a) compares the HT strengths of Nb15Ta10W75 and
where Δσo is the lattice friction stress of the matrix which is estimated
(Nb15Ta10W75)98.5C1.5 with those of other RHEAs reported in literature
using the weighed average of the lattice friction stresses (oj) of the
[67-73]. It shows (Nb15Ta10W75)98.5C1.5 exceeds all the others at

∆σ
Δσ
∆σ
Δσ
Strengthen Contribution
S
GB
DIS
Δσ
Experimental value
Nb15Ta10W75
(Nb15Ta10W75)98.5C1.5
P

## 32.9. %

Δσ0
(Nb,.Ta, Wz5)os 5C

## 28.3. %

Strength (MPa)
75' 98.5
1.5
Nb.Ta..W

## 25.8. %

ΔσsSH
iΔσsSH

## 22.2. %

## 18.8. %

σGBΔσGB

## 17.7. %

## 22.5. %

ΔσDIS
IσDIS

## 20.6. %

## 0.0. %

Δσp

## 11.0. %

Theo.
Exp.
Theo.
Exp.
Fig. 13. Comparison of Nb15Ta10W75 versus (Nb15Ta10W75)98.5C1.5 in terms of strengthening mechanisms contributions and proportions.
Compressive strength (MPa)
Softening temperature ()
VZ

## 5.8. %

Yc
X
-1450 °C -
Temperature (C)
Atomic mismatch (%)
Nb15Ta10W75
(Nb15Ta10W75)98.5C1.5
NbMoTaWV
[66]
Hf0.5MoNbTaW[66]
HfMoNbTaW
[66]
NbMoTaWTi
[67]
NbTaW0.5
[68]
NbTaW0.5(Mo2C)0.10
NbMoTaWVTi
[68]
NbTaW0.5(Mo2C)0.20
[68]
[69]
Nb2MoWC0.96
[70]
Hf 0.25NbTaW0.5
Wo.s(TaTiVCr)0.5
[71]
Hf 0.25NbTaW0.5C0.15
, [71]
Hf 0.25NbTaW0.5C0.2571]
HfMoNbTaZr
[72]
HfMoNbTaTi
[72]
Fig. 14. A comparison of the (a) HT strengths and (b) softening temperatures and atomic mismatch of various RMPEAs with those examined in this study.
various testing temperatures. The softening temperature (Tc) and atomic
The impact of NbC on the HT properties is evaluated by analyzing the
mismatch degree (δr) are important aspects of HT strength of alloys and
work-hardening rates and dislocation types at different compression
hence can serve as the critical parameters for evaluation [29]. As the
temperatures. The work-hardening curves, classified into two types
temperature is increased, a transition in the dominant deformation
(Figs.15 (a1) and (a2)), reveal distinct behaviors based on the
mechanism—from screw to edge dislocation mobility dominated regi-
compression temperature. Below 1400 °C, the work hardening curves of
mes—occurs, and Tc reflects this transition temperature range (usually
Nb15Ta10W75 and (Nb15Ta10W75)98.5C1.5 exhibit high work-hardening

## 0.30.5. times melting temperature) [74,75]. A higher Tc is beneficial for

rates, indicating strong HT softening resistance. Above 1400 C, the
maintaining strength at higher temperatures. δr reflects the degree of
work hardening behavior shows a significant transformation, with a
lattice mismatch and is related to the resistance of dislocation movement
sharp decrease in hardening rate with true strain in stage I (εT <10 %),
at HT, and can be estimated using the following equation:
indicating that dislocation slip occurs readily at this temperature. Be-
sides, (Nb15Ta10W75)98.5C1.5 exhibits a lower slope in the work-
hardening curve (KwH) than Nb15Ta10W75, indicating stronger resis-
n
ri
tance to HT deformation. The difference in work-hardening ability is
δr = 100

## 1. −

(27)
n
closely related to temperature and micro-deformation mechanisms. To
i=1
∑
this end, the phase type and ρ of compressed samples subjected to εT =10
i=1
% at 1400 and 1600 °C are evaluated using XRD, as shown in Fig. 15(b).
where c is the atomic fraction of the ith element and ri is the atomic
NbC nano-precipitates still exist in (Nb15Ta10W75)98.5C1.5 after under-
radius. Fig.14(b) compares the values of Tc and δr of Nb15Ta10W75 and
going HT compression with εT =10 %, which is beneficial for HT
(Nb15Ta10W75)98.5C1.5 with the respective values reported for other
strength. The value of ρ, estimated using the Scherrer formula, in
RMPEAs. It is observed that (Nb15Ta10W75)98.5C1.5 has the highest Tc
(Nb15Ta10W75)98.5C1.5 is higher than that in Nb15Ta10W75 after HT
and δr values, consistent with its superior HT strength.

(a1)
Nb15Ta10W75
[(Nb15Ta10W75)98.5C1.5- 1000 C
(b)
(Nb15Ta10W75)98.5C1.5(ε=10 %)
(110)
-1400 C-1600 °C
°C
(111)
Nb15Ta10W75(ε=10 %)
Intensity
Hardening
-1400 °C-1600
ºC
BCC
•B2(NbC)
K
WH
KwH
(211)
(200)
Stage I
Stage II
(220)
Stage
I
Stage II
I
True strain
(%)
True
strain
(%)
2-Theta
Nb15Ta10W75-1400°C
Nb15Ta10W75-1600°C
(Nb15Ta10W75)98.5C1.5-1400°C
(Nb15Ta10W75)98.5C1.5-1600°C
(c1)
(c2)
Z.A. [111]BcC
Z.A.[
[001]BCC
(c3)
Z.A.
[001]Bcc
(c4)
Z.A. [11]BCC
g=100
Screw-Edge
g=
g
U
-
g
GB
C
GB0
-D
-
-
-rD
-
b=11/2[111]
a
-
b-+1/2(111]
b=± 1/2[111]
b=± 1/2[001]
b=± 1/2[111]
GB
Nb15Ta10W75 compressed at (c1) 1400 C and (c2) 1600 C, (Nb15Ta10W75)98.5C1.5 compressed at (c3) 1400 C and (c4) 1600 C.
compression (Table 4), which benefits the HT strength [76].
were compression tested at 1600 °C (εT =10 %). The accumulation of
Furthermore, the type of dislocation dominating the deformation
dislocations at the GBs, which is also observed, increases the back stress
plays a critical role in determining the HT strength [75]. The maximum
that could hinder dislocation glide. The average dislocation velocity (νd)
Tc of both Nb15Ta10W75 and (Nb15Ta10W75)98.5C1.5 is ab0ut 1500 °C.
is estimated using the Orowan equation [78,79]:
Thus, the compression temperature of 1600 C marks the transition
E
(28)
Vd =
between dislocation types. At temperatures below Tc, work-hardening
ρb
curves dominated by the screw dislocations show continuous deforma-
tion behavior, while deformation dominated by the edge dislocations at
EL
(29)
^3
H
temperatures above Tc results in a rapid decrease in the hardening rate
[77]. The observed hardening curve conforms to such a change in the
where ρ is obtained from the XRD results (see Table 4), εy is the strain
pattern, supporting the hypothesis that the HT strength transitions from
rate, H is the height of the HT compressed sample, εL is a constant
screw-dominated to edge-dominated dislocation motion. To further
loading rate of HT compression. At temperatures below Tc, only pure
clarify the types of dislocations operating at different temperatures,
edge dislocations survived in the compressed samples Nb15Ta10W75 and
two-beam BF TEM images are obtained from compressed samples sub-
(Nb15Ta10W75)98.5C1.5. This is because of the difficulty of screw dislo-
jected to εT =10 % at 1400 and 1600 °C. Results are shown in Figs.15
cation cores dissociating into nonplanar structures during motion, while
(c1-c4). The g vector is marked in each image, and its direction is denoted
edge dislocations tend to divide into segments that slip more easily along
by a white arrow. b is determined using the g × b = 0 condition; detailed
the glide planes [72]. Therefore, screw dislocations are more prone to
information is provided in Supplementary-Note 5 of supplementary
annihilation than edge dislocations, leading to the survival of pure edge
material. (Nb15Ta10W75)98.5C1.5 shows more dislocation lines than
dislocations and dominating the slip rate and HT strength. The estimated
Nb15Ta10W75, consistent with the higher ρ results obtained using XRD.
velocity of screw dislocations (νds) in Nb15Ta10W75 and
The dislocations are colored according to their respective orientation
(Nb15Ta10W75)98.5C1.5 compressed at 1400 °C are 1.51 and 1.30 mm/s,
relationships with b. It is found that there are two kinds of dislocations
respectively. When the temperature exceeds Tc, numerous Frank-Read
based on their orientation relationship with different b: ± 1/2[111] in
sources are activated for dislocation multiplication, promoting the
red, and ± 1/2[001], ± 1/2[111], ± 1/2[1−11] in orange. It is observed
glide of the screw dislocations, whereas edge dislocations are less
that only the edge dislocations exist in the Nb15Ta10W75 and
influenced. With deformation, the speed of screw dislocations becomes
(Nb15Ta10W75)98.5C1.5 samples compressed to εT of 10 % at 1400 °C. In
comparable to those of edge dislocations (vde), consequently maintain-
contrast, both screw and edge dislocations coexist in the samples that
ing the HT strength. The screw and edge dislocations in Nb15Ta10W75
and (Nb15Ta10W75)98.5C1.5 at 1600 °C have similar mobilities, with νds =
Table 4

## 2.36. mm/s for Nb15Ta10W75 and vds = Vde = 2.21 mm/s for

Vde
The ρ values of samples compressed at 1400 °C and 1600 °C with εT =10 %.
(Nb15Ta10W75)98.5C1.5. The HT strength of (Nb15Ta10W75)98.5C1.5 in-
creases by about 111 MPa at 1400 °C and 110 MPa at 1600 °C compared
Nb15Ta10W75
(Nb15Ta10W75)98.5C1.5
to Nb15Ta10W75, attributed to the impediment of screw/edge dislocation
movement by the NbC particles. Based on these results, it can be
ρ (1014/m²)
8.35
5.35
9.67
5.71
concluded that the NbC nano-precipitates can stably survive at HT and

effectively impede screw/edge dislocation movement at HT, leading to
higher ρ and improved HT strength.
the online version, at doi:10.1016/j.actamat.2025.121325.
References

## 5. Summary and conclusions

[1]
E.P. George, D. Raabe, R.O. Ritchie, High-entropy alloys, Nat. Rev. Mater. 4 (2019)
A design strategy for composite RMPEAs, suitable for LPBF via
515534.
[2]
Y.K. Zhao, D.H. Lee, M.Y. Seok, J.A. Lee, M.P. Phaniraj, J.Y. Suh, H.Y. Ha, J.Y. Kim,
ceramic powder addition and in-situ nano-precipitate formation, was
U. Ramamurty, J.I. Jang, Resistance of CoCrFeMnNi high-entropy
alloy to gaseous
developed to simultaneously enhance printability, reduce anisotropy,
hydrogen embrittlement, Scripta. Mater. 135 (2017) 5458.
and sustain strength at HT conditions. The main conclusions of this
[3]
D.H. Lee, M.Y. Seok, Y.K. Zhao, I.C. Choi, J.Y. He, Z.P. Lu, J.Y. Suh, U. Ramamurty,
M. Kawasaki, T.G. Langdon, J.I. Jang, Spherical nanoindentation creep behavior of
study are the following.
nanocrystalline and coarse-grained CoCrFeMnNi high-entropy
alloys,
Acta. Mater.

## 109. (2016) 314322.

1) By estimating the solid solubility and critical re-precipitation
[4]
J. Gubicza, A. Heczel, M. Kawasaki, J.K. Han, Y.K.
Zhao,
Y.F. Xue,
S.
Huang, J.
L. Lábár, Evolution of microstructure and hardness
in
Hf25Nb25Ti25Zr25
high-
amounts of the in-situ nano-precipitates, and measuring the pow-
entropy alloy during high-pressure torsion, J. Alloy. Compd.
.788
(2019)
318328.
der flowability and laser absorptivity, we found that adding 1.5 at. %
[5]
A.H. Jeon, Y.K. Zhao, Z. Gao, J.Y. Suh,
H.J.
Ryu,
H.S.
Kim,
U. Ramamurty, J.
WC powder to matrix powders promotes the formation of in-situ
I. Jang, Stochastic nature of incipient plasticity
in a body-centered cubic medium-
entropy alloy, Acta. Mater. 278 (2024) 120244.
phase and improves the print quality.
[6]
R. Feng, B. Feng, M.C. Gao, C. Zhang, J.C. Neuefeind, J.D. Poplawsky, Y. Ren,
2) Incorporating 1.5 at. % WC powder also enhanced the laser ab-
K. An, M. Widom, P.K. Liaw, Superior High-Temperature Strength in a
sorptivity from 71 % to 86 % without compromising powder flow-
Supersaturated Refractory
High-Entropy
Alloy,
Adv. Mater. 33
(48) (2021)
ability, expanding printing ranges of about 50 Jmm-3, reducing LOF
2102401.
[7]
P. Kumar, S. Huang,
D.H.
Cook,
K.
Chen,
U.
Ramamurty, X.P. Tan, R.O. Ritchie,
pores, and improves the printed part density from 99.2 ± 0.15 % to
A strong fracture-resistant high-entropy
alloy
with
nano-bridged honeycomb

## 99.5. ± 0.1 %.

microstructure intrinsically
toughened
by
3D-printing,
Nat.
Commun.
(2024)
3) During LPBF, the added WC powder particles dissolve in the melt
841.
[8]
O.N. Senkov, D.B. Miracle, K.J. Chaput, J.P.
Couzinie,
Development
and
pool and the C combines with Nb to form NbC in-situ. These pre-
exploration of refractory high entropy
alloys
-A
review,
J.
Mater.
Res. 33
(19)
cipitates, subsequently, act as heterogeneous nucleates to shorten
(2018) 30923128.
solidification distance and inhibit columnar grain growth. As a
[9]
O.N. Senkov, G.B. Wilks,
D.B.
Miracle,
C.P.
Chuang,
P.K.
Liaw,
Refractory
high-
entropy alloys, Intermetallics
(9)
(2010)
17581765.
result, a substantial reduction in microstructural and mechanical
[10]
C.Y. Yap, C.K. Chua,
Z.L.
Dong,
Z.H.
Liu,
D.Q.
Zhang,
L.E.
Loh,
S.L.
Sing,
Review of
anisotropy is obtained. Moreover, (Nb15Ta10W75)98.5C1.5 exhibits a
selective laser melting:
materials
and
applications,
Appl.
Phys.
Rev. 2
(4)
(2015)
superior yield strength at RT, which is attributed to the grain
041101.
[11]
Z. Li, Y.N. Cui, W.T. Yan, D. Zhang, Y. Fang,
Y.J.
Chen,
Q.
Yu,
G.
Wang,
H.
Ouyang,
boundary, dislocation, and precipitation strengthening mechanisms.
C. Fan, Q. Guo, D.B. Xiong, S.B. Jin, G. Sha,
N.
Ghoniem,
Z.
Zhang,
Y.M. Wang,
The HT strength of (Nb15Ta10W75)98.5C1.5 also increased due to the
Enhanced strengthening and hardening
via self-stabilized
dislocation network in
additively manufactured metals, Mater. Today.
suppression of dislocation mobility by the NbC nano-precipitates.
(2021)
7988.
[12]
D. Wang, L. Liu, G. Deng, C. Deng, Y. Bai, Y. Yang,
W.
Wu, J.
. Chen,
Y. Liu, Y. Wang,
X. Lin, C. Han, Recent progress on Additive manufacturing
of multi-material

## CRediT Authorship

structures with laser powder bed fusion, Virtual.
Phys. Prototy. 17 (2) (2022)
329365.
[13] S. Chandra, J. Radhakrishnan, S. Huang, S.Y. Wei, U. Ramamurty, Solidification in
Ran Duan: Writing - review & editing, Writing original draft,
metal additive manufacturing: challenges, solutions, and opportunities, Prog.
Validation, Methodology, Data curation. Yakai Zhao: Writing review
Mater. Sci. 148 (2025)
101361.
[14]
A. Roh, D. Kim, S. Nam,
, D.I. Kim, H.Y. Kim, K.A. Lee, H. Choi, J.H. Kim, NbMoTaW
& editing, Validation, Supervision. Xiaodan Li: Resources, Methodol-
refractory high entropy
y alloy composites strengthened by in-situ metal-non-metal
ogy. Jintao Xu: Validation, Investigation. Meng Qin: Validation,
compounds, J. Alloy. Compd. 822 (2020) 153423.
Investigation, Data curation. Kai Feng: Writing - review & editing,
[15] J. Sun, P. Kumar, P. Wang, U. Ramamurty, X.H.
. Qu, B.C. Zhang,
, Effect of columnar-
to-equiaxed microstructural transition on the fatigue performance of a laser
Project administration, Methodology, Funding acquisition, Conceptu-
powder bed fused high-strength Al alloy, J. Mater. Sci. Technol. 227
(2025)
alization. Zhuguo Li: Resources, Project administration, Methodology,
276288.
Funding acquisition. Beibei Xu: Visualization, Validation, Software,
[16]
S.Y. Wei, P. Wang, L.
Zhang, U. Ramamurty,
Grain
morphologies
in
additively
Resources, Formal analysis, Data curation. Upadrasta Ramamurty:
manufactured alloys: from solidification
fundamentals
to
advanced
microstructure
control, J. Mater. Sci.
Technol.
(2025)
133145.
Writing - review & editing, Supervision, Methodology, Investigation,
[17]
D.Y. Zhang, A. Prasad,
M.J.
Bermingham,
C.J.
Todaro,
M.J.
Benoit,
M.N.
Patel,
Formal analysis, Data curation, Conceptualization.
D. Qiu, D.H. StJohn,
M.
Qian,
M.A.
Easton,
Grain
Refinement
of
Alloys
in
Fusion-
Based Additive Manufacturing
Processes,
Metall.
Mater.
Trans. A.
(2020)
43414359.

## Declaration of Interest

[18]
Y.K. Zhao, K.B. Lau, W.H. Teh, J.J. I
Lee,
F.X.
Wei,
, M.
Lin,
P.
Wang,
C.C.
Tah,
U. Ramamurty, Compositionally graded CoCrFeNiTix high-entropy
alloys
The authors declare that they do not have any commercial or asso-
manufactured by laser powder bed fusion: a
combinatorial
assessment,
Alloy.
Compd. 883 (2021) 160825.
ciative interest that could have appeared to influence the work reported
[19]
Y.X. Wan, Study On the Preparation and Mechanical Properties of Rare
Metals
Nb/
in this paper.
Mo/Ta/W Based Ultra-High-Temperature High-entropy Alloys, China University
of
Mining and Technology, 2021.
[20]
T.K. Kai, H.
Hsuan,
, W.W. Ren,
Y.J. Wei, T.C.
Wei,
Edge-dislocation-induced

## Acknowledgements

ultrahigh elevated temperature strength of HfMoNbTaW refractory
high-entropy
alloys, Sci. Technol. Adv.
Mat.
(1)
(2022)
642654.
[21]
L. Wang, Z.X. Guo,
G.C.
Peng,
S.W.
Wu,
Y.M.
Zhang,
This work was financially supported by National Key R&D Program
W.T.
Yan,
Evaporation-
Induced Composition Evolution
in
Metal
Additive
Manufacturing,
Adv.
Funct.
of China (No. 2022YFB4602102), Shanghai Collaborative Innovation
Mater. 24 (2024) 12071.
Project (No. HCXBCY-2023064). We would like to acknowledge the
[22]
Z. Sun, Y. Ma, D. Ponge, S. Zaefferer,
E.A.
Jägle,
B.
Gault,
A.D.
Rollett,
D.
Raabe,
support from the Instrumental Analysis Center of Shanghai Jiao Tong
Thermodynamics-guided alloy and process design
for
dditive
manufacturing,
Nat.
Commun. 13 (1) (2022)
4361.
University and Instrument and equipment sharing platform of School of
[23]
R. Duan, J.T. Xu, Y.K. Zhao,
Q.J. Zhou,
Z.Y.
Yan,
Y.
Xie,
P.
Dong,
K.
Feng,
Z.G. Li,
Materials Science and Engineering, SJTU. YZ would like to thank the
X.B. Liang, U. Ramamurty,
High entropy alloys
amenable
for
laser
powder
bed
fusion: a thermodynamics
guided machine learning
support by A*STAR via the Advanced Models for Additive
search,
Addit.
Manuf.
(2024) 104195.
Manufacturing (AM2) programme (No. M22L2b0111).
[24]
Q.Y. Tan, Y. Yin, M.X. Zhang, Comparison
n of the Grain-Refining
Efficiencies of Ti
and LaB6 Inoculants in Additively Manufactured 2024
Aluminum
Alloy:
the
Important Role of Solutes, Metals-Basel 13
(8) (2023) 1490.

## Supplementary Material

[25] C. Guo, G. Li, S. Li, X.G. Hu, H.X. Lu, X.G. Li, Z. Xu, Y.H. Chen, Q.Q. Li, J. Lu,
Q. Zhu, Additive manufacturing of Ni-based superalloys: residual stress,

## Supplementary Material

Sci. 5 (1) (2023) 5377.
[51] Y.A. Coutinho, S.C.K. Rooney, E.J. Payton, Analysis of ebsd grain size
[26]
C.L. Tan, J. Zou, D. Wang, W.Y. Ma, K. Zhou, Duplex strengthening
measurements using microstructure simulations and a customizable pattern
via SiC addition
matching library for grain perimeter estimation,
, Metall. Mater. Trans. A. 48 (5)
Part b-Eng. 236
(2017) 23752395.
(2022) 109820.
[27]
Z. Chen, X.L. Wen, W.L. Wang, X. Lin,
[52]
H.O.
Yang,
Z.
Jiang,
H. Li, N. Li, Engineering
L.Y.
Chen,
H.B. Wu, W.
fine grains, dislocations
and
precipitates
for
enhancing the
alloys, J. Mater. Process. Tech. 19
strength of TiB2-modified CoCrFeMnNi
(2022) 194207.
high-entropy
alloy
using
laser
powder bed
[53]
fusion, J. Mater.
Res. Technol. 26
(2023)
-1213.
Y. He, Grain refinement of Ti6Al4V by incorporating
[28]
J. Hu, X. Lin, Y.l. Hu, High
in-situ TiB nanowhiskers in
wear resistance
and
strength
of
Hastelloy
X reinforced
laser melting depositions, J. Mater. Process. Tech. 27
with TiC fabricated by laser powder bed f
(2023)
28932901.
fusion
additive
manufacturing,
Appl Surf
[54]
S.N. Tedman-Jones, S.D. McDonald, M.J. Bermingham,
Sci 648 (2024)
D.H.
Stjohn,
, M.
159004.
S. Dargusch, Investigating the morphological effects of solute
on
the
β-phase in as-
[29]
R. Duan, Y.K. Zhao,
J.T. Xu,
Q.J. Zhou,
Z.Y.
Yan,
Y.
Xie,
P.
Dong,
K.
Feng, Z.G. Li,
cast titanium alloys, J. Alloy. Compd. 788 (2019) 204214.
B.B. Xu, X.B. Liang,
U. Ramamurty,
, Additive
manufacturing
of
refractory multi-
[55]
B. Yin, H.W. Ma, Y.D. Wang, H. Zhao, G. Jin, J.M. Wang, Modeling and application
principal element alloy with ultrahigh-temperature
strength
via
simultaneous
enhancements
sin
printability and solid solution
hardening,
Addit.
Manuf. 91
grain size, J. Alloy. Compd. 739 (2018) 901908.
(2024) 104340.
[56]
S.N. Tedman-Jones, M.J. Bermingham, S.D. McDonald, D.H. StJohn, M.
[30]
J.L. Zhang, J.B. Gao,
B. Song, L.J. Zhang,
C.J.
Han,
C.
Cai,
K.
Zhou, Y.S. Shi,
S. Dargusch, Titanium sponge as a source of native nuclei in titanium alloys,
A novel crack-free Ti-modified Al-Cu-Mg alloy
y designed for selective laser melting,
J. Alloy. Compd. 818 (2019) 153353.
Addit.
Manuf.
(2021)
101829.
[57]
H.Y. Liu, S. Wang, J. Liang, H. Hu,
Q.T. Li, H.R. Chen,
Effect of Lanthanum Oxide
[31]
Q. Ge,
D.D.
Gu,
D.H.
Dai,
C.L. Ma,
Y.X.
Sun,
X.Y.
Shi,
Y.Z.
Li,
H.M. Zhang, H.
on the Microstructure and Properties of Ti-6Al-4V
Alloy during
CMT-Additive
Y. Chen,
Mechanisms
melting
of
laser
energy
absorption
and
behavior during
Manufacturing, Crystals 13
(3) (2023) 515.
selective
laser melting
of
titanium-matrix
composite:
role
of
ceramic addition,
[58]
Q.Y. Tan, M.X. Zhang, Recent advances in inoculation
treatment for
powder-based
J. Phys. D. Appl.
Phys. 54
(2021)
115103.
additive manufacturing of aluminium alloys,
Mat.
. Sci.
Eng.
R.
(2024)
100773.
[32]
M.A. Balbaa, A.
Ghasemi, E. Fereiduni, M.A. Elbestawi,
S.D. Jadhav, J.P. Kruth,
[59]
Y.N. Zhao, T. Ma, Z.J. Gao, Y.Y. Feng, C. Li, Q.Y. Guo, Z.Q. Ma,
Y.C.
Liu,
Significant
reduction of grain size and texture intensity
in
laser powder
bed
fusion
fabricated
alloy, Addit. Manuf. 37 (2021) 101630.
nickel-based superalloy by increasing constitutional supercooling,
Compos. Part. B-
[33]
Wang,
,L. Huang,
Eng. 266 (2023) 111040.
[60]
Z.Y. Ji, C.L. Qiu, Achieving
superior high-temperature strength
in an
additively
printed by selective laser melting, Intermetallics
(2019)
2432.
manufactured high-entropy alloy by controlled heat treatment,
Appl. Mater.
[34]
P. Gu, T. Qi, L. Chen, T. Ge, X. Ren, Manufacturing
and
analysis
of VNbMoTaW
Today. 40 (2024) 102412.
laser
melting,
Int. J. Refract.
[61]
H.B. Dai, H.W. Zhao,
Y.H.
Xia,
X.Y.
Cai,
, B.L. Dong,
S.B.
Lin,
Y.
Zhao,
Wire
arc
Met. H. 54 (11) (2022) 115103.
additive manufacturing
of ZL205A: heat input effect on
the forming quality, pore
[35]
D.W. Wang,
H.L.
Han, B. Sa, K.L. Li, J.J. Yan, J.Z. Zhang,
J.G. Liu, Z.D. He,
defects and mechanical properties, J. Alloy.
Compd.
(2024)
175777.
[62]
X.H. Du, W.P. Li, H.T. Chang, T. Yang,
G.S.
Duan,
B.L.
Wu,
J.C.
Huang, F.R. Chen,
Adv. 5
(10) (2022) 34.
C.T. Liu, W.S. Chuang, Y. Lu, M.L. Sui,
E.W.I
Huang,
Dual heterogeneous structures
[36]
J.Y. He,
, H. Wang, H.L. Huang, X.D. Xu, M.W. Chen, Y. Wu, X.J. I
Liu, T.G. Nieh,
lead to ultrahigh strength and uniform
ductility
in
a
Co-Cr-Ni medium-entropy
K. An, Z.P. Lu, A precipitation-hardened high-entropy
alloy
with outstanding
alloy, Nat. Commun. 11 (1) (2020)
2390.
tensile properties, Acta. Mater. 102 (2016) 187196.
[63]
W. Fu, C.N. Li, X.J. Di, J.J. Wang, K.J. Fu,
W.Y. Hu, D.P.
Wang,
Effect of peak
[37]
Y.H. Zhao, X.Z. Liao, Z. Jin, R.Z. Valiev, Y.T. Zhu, Microstructures and mechanical
temperature on nanoscale Cu-rich re-precipitation behavior and strength-
properties of ultrafine grained 7075 Al alloy processed by ECAP and their
toughness of welding heat affected zones for Cu-bearing
high strength steel, Mater.
evolutions during annealing, Acta. Mater. 52 (15)
(2004) 45894599.
Charact. 199 (2023) 112809.
[38]
N.T. Tayade, M.P. Tirpude,
, Frustrated microstructures composite PbS material's
[64]
X.F. Xie, Z.M. Xie, R. Liu, Q.F. Fang, C.S. Liu,
,W.Z. Han,
X.
Wu,
Hierarchical
size perspective from XRD by variant models of Williamson-Hall
plot method,
microstructures enabled excellent low-temperature strength-ductility synergy
in
B. Mater. Sci. 46 (20) (2023) 102843.
bulk pure tungsten, Acta. Mater. 228 (2022) 165187.
[39]
H.W. Deng, M.M. Wang, Z.M. Xie, T. Zhang, X.P. Wang, Q.F. Fang, Y. Xiong,
[65]
D.H. Lee, J.A. Lee, Y.K. Zhao, Z.P. Lu, J.Y. Suh, J.Y. Kim,
U. Ramamurty,
Enhancement of strength and ductility in non-equiatomic CoCrNi medium-entropy
M. Kawasaki, T.G. Langdon, J.I. Jang, Annealing
effect
on
plastic flow in
alloy at room temperature via transformation-induced plasticity,
Mat.
. Sci. Eng. A-
nanocrystalline CoCrFeMnNi high-entropy
alloy:
a nanomechanical
analysis, Acta.
Struct. 804 (2021) 140516.
Mater. 140 (2017) 443451.
[40]
D. Thomas, D. Patricia, C.J. Marc,
L.
Williams, F.D.
Geuser,
D. Alexis,
Size
[66]
I. Toda-Caraballo, A general formulation for solid
solution hardening effect in
distribution and volume fraction of T1 phase precipitates from TEM images: direct
multicomponent alloys, Scripta. Mater. 127
(2017)
113117.
s and related correction,
Micron 78 (2015)
measurements
1927.
[67]
J.P. Couzinie, O.N. Senkov, D.B. Miracle,
G.
Dirras,
Comprehensive
data
[41]
A. Roy, P. Sreeramagiri, T. Babuska,
B. Krick, P.K. Ray, G. Balasubramanian,
compilation on the mechanical properties
of refractory
high-entropy
y alloys, Data.
Lattice distortion as an estimator of solid
solution
strengthening in high-entropy
Brief. 21 (2018) 16221641.
alloys, Mater. Charact. 172 (2021)
) 110877.
[68]
Z.D. Han, N. Chen, S.F. Zhao, L.W. Fan,
G.N.
Yang,
Y.
Shao,
K.F.
Yao,
Effect of Ti
[42]
X.C. Yang, X.J. Di, Q.Y. Duan, W. Fu, L.Z. Ba, C.N. Li, F
Effect of precipitation
additions on mechanical properties of NbMoTaW
and
VNbMoTaW
refractory
high
evolution of NiAl and Cu nanoparticles on strengthening
mechanism of low carbon
entropy alloys, Intermetallics

## 84. (2017)

153157.
ultra-high strength seamless tube steel, Mat. Sci. Eng. A-Struct. 872 (2023) 144939.
[69]
S. Wu, D. Qiao,
H. Zhao, J. Wang, Y. I
Lu,
A
novel
NbTaW0.5(Mo2C)x refractory
[43]
S. Yin, Y. Zuo, A.A. Odeh, H. Zheng, X.G. Li, J. Ding,
, S.P. Ong,
M.
Asta, R.
high-entropy alloy with excellent mechanical
properties,
J.
Alloy.
Compd.
O. Ritchie, Atomistic simulations of dislocation mobility in refractory high-entropy
(2021) 161800.
alloys and the effect
of chemical short-range order,
Nat.
Commun.
. 12 (1) (2021)
[70]
S. Alvi, O.A. Waseem,
F. Akhtar, High
n Temperature Performance of Spark Plasma
4873.
Sintered W0.5(TaTiVCr)0.5 Alloy, Metals-Basel 10 (11) (2020) 1512.
[44]
Y.G. Liu, J.Q. Zhang, R.M. Niu, M. Bayat, Y. Zhou,
Y.
Yin,
Q.Y.
Tan, S.Y. Liu, J.
[71]
Y. Zhang, Q. Wei, P. Xie, X. Xu, An ultrastrong niobium alloy
enabled by refractory
H. Hattel, M.Q. Li, X.X. Huang, J. Cairney, Y.S. Chen, M. Easton, C. Hutchinson, M.
carbide and eutectic structure, Mater. Res. Lett. 11
(3)
(2022) 169178.
X. Zhang, Manufacturing of high strength and high conductivity copper with laser
[72]
S. Wu, D. Qiao, H. Zhang, J. Miao, H. Zhao, J. Wang,
Y. Lu,
T.
Wang, T. Li,
powder bed fusion, Nat. Commun. 15 (2024) 1283.
Microstructure and mechanical properties of C1
Hf0.25NbTaW0.5
refractory high-
[45]
D. Huang, J. Yan, X. Zuo, Co-precipitation kinetics,
microstructural evolution and
entropy alloys at room and high temperatures,
J.
Mater.
Sci.
Technol.
(2022)
interfacial segregation in multicomponent nano-precipitated steels, Mater. Charact.
229238.

## 155. (2019) 109786.

[73]
K.K. Tseng, C.C. Juan, S. Tso, H.C. Chen, C.W.
Tsai,
J.W.
Yeh,
Effects
of Mo,
Nb,
Ta,
[46]
X.Q. Liu, C.C. Wang, Y.F. Zhang, L.Y. Wang, W. Xu, Design of a 2.7 GPa ultra-high-
Ti, and Zr on Mechanical Properties of Equiatomic
Hf-Mo-Nb-Ta-Ti-Zr
Alloys,
strength high Co-Ni secondary hardening steel by two-step nano-size precipitation
Entropy-Switz 21 (1) (2018)
15.
tailoring, J. Mater. Process. Tech. 28 (2024) 42124221.
[74]
C. Baruffi, F. Maresca, W.A. Curtin, Screw vs.
edge
dislocation
strengthening
S. Guan, K. Solberg, D. Wan, F. Berto, T. Welo, T.M. Yue,
in
[47]
K.C. Chan,
Formation of
body-centered-cubic high
h entropy alloys and implications
for
guided
alloy
design,
fully equiaxed grain microstructure in additively manufactured
AlCoCrFeNiTi0.5
Mrs. Commun. 12
(6) (2022) 11111118.
high entropy alloy, Mater. Design. 184 (2019)
108202.
[75]
W. Huang, J. Hou,
X.
Wang, J.
Qiao,
Y. Wu,
Excellent
[48]
X. Li, Y. Feng, B. Liu, D. Yi, X. Yang, W. Zhang, G. Chen, Y. Liu, P. Bai, Influence of
room
-temperature
tensile
ductility in
as-cast Ti37V15Nb22Hf23W3 refractory
NbC particles on microstructure and mechanical properties of AlCoCrFeNi high-
high
entropy
alloys,
Intermetallics 151
(2022)
107735.
entropy alloy coatings prepared by laser cladding, J. Alloy. Compd. 788 (2019)
[76]
X.R. Zhou, X.Y. Wang, L. Fey, S.C. He, I. Beyerlein,
485494.
P.H.
Cao,
J.
Marian,
dislocation glide and strengthening mechanisms
Models
of
[49]
G. Neumann, C.
Tuijn, Self-diffusion and Impurity Diffusion
in
bcc
complex
in Pure metals:
concentrated
alloys, Mrs. Bull. 12 (
Handbook of Experimental Data, Elsevier, 2011.
(2023) 11111118.
G. Wang,
Y.M. Zhang,
[50]
B.K. Zou, Y. Liu, S.Q. Zheng, X.C. Li,
W.T. Yan, Z. Li, Y.
M. Wang,
Enhanced
plasticity
due to melt pool flow induced uniform dispersion of
reinforcing particles
in additively
y manufactured metallic composites, Int. J.
Plasticity. 164
(2023) 103591.

[77] C. Xiang, C. Han, M. Siming, Insights into flow stress and work hardening
behaviors of a precipitation hardening AlMgScZr alloy:
[79] P. Kumar, M. Michalek, D.H. Cook, H. Sheng, K.B. Lau, P. Wang, M.W. Zhang, A.
Int. J. Plasticity. 172 (2024) 103852.
experiments and modeling,
M. Minor, U. Ramamurty, R.O. Ritchie, On the strength and fracture toughness of
[78]
Y. Lu, Y.H. Zhang, E. Ma, W.Z. Han, Relative mobility
an additive manufactured CrCoNi medium-entropy alloy, Acta. Mater. 258 (2023)
dislocations controls the ductile-to-brittle transition
of screw
versus edge
119249.
Usa. 118 (37) (2021) 21105.
in metals, P. Natl. Acad. Sci.