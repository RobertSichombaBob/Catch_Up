"""Starter catalogue: 6 subjects, 6 courses, 36 short lessons.

Each lesson follows the same shape: the idea, the key fact, a worked
example, and a "check yourself" question with a hidden answer. Tutors
replace and extend these in the tutor studio.
"""

SUBJECTS = [
    # slug, name, tagline, icon, colour, order
    ('mathematics', 'Mathematics', 'Pure maths, statistics and mechanics', 'sigma', '#4F46E5', 1),
    ('physics', 'Physics', 'Mechanics, waves, electricity and fields', 'atom', '#0E7490', 2),
    ('chemistry', 'Chemistry', 'Physical, organic and inorganic chemistry', 'flask', '#B45309', 3),
    ('biology', 'Biology', 'Cells, genetics, physiology and ecology', 'dna', '#15803D', 4),
    ('computer-science', 'Computer Science', 'Programming, algorithms and systems', 'code', '#7C3AED', 5),
    ('data-science', 'Data Science', 'Statistics, Python and machine learning', 'database', '#DB2777', 6),
]

TUTORS = [
    # email, first, last, headline, subjects, degree
    ('mwila.banda@catchup.example', 'Mwila', 'Banda', 'Mathematics and data science tutor, 9 years',
     ['mathematics', 'data-science'], 'BSc Mathematics with Education'),
    ('joseph.tembo@catchup.example', 'Joseph', 'Tembo', 'A-level and first-year Physics lecturer',
     ['physics'], 'BSc Physics with Education'),
    ('chipo.phiri@catchup.example', 'Chipo', 'Phiri', 'Chemistry teacher and exam marker',
     ['chemistry'], 'BSc Chemistry with Education'),
    ('natasha.zulu@catchup.example', 'Natasha', 'Zulu', 'Biology teacher, A-level and university',
     ['biology'], 'BSc Biological Sciences with Education'),
    ('mutale.mulenga@catchup.example', 'Mutale', 'Mulenga', 'Software engineer and computing lecturer',
     ['computer-science'], 'BEng Computer Engineering'),
]

ADMINS = [('admin@catchup.example', 'Platform', 'Admin'), ('operations@catchup.example', 'Operations', 'Team')]


def lesson(title, idea, key, example, question, answer):
    return {
        'title': title,
        'content': (
            f'<p>{idea}</p>'
            f'<div class="callout key"><strong>Key idea.</strong> {key}</div>'
            f'<h2>Worked example</h2><div class="callout example">{example}</div>'
            f'<h2>Check yourself</h2><p>{question}</p>'
            f'<details><summary>Show the answer</summary><p>{answer}</p></details>'
        ),
    }


COURSES = [
    {
        'subject': 'mathematics', 'tutor': 'mwila.banda@catchup.example', 'level': 'both', 'year': '',
        'title': 'Pure Mathematics: Calculus Foundations',
        'summary': 'Differentiation and integration from first principles to exam-ready technique.',
        'outcomes': 'Differentiate polynomials, products and quotients\nFind stationary points and their nature\n'
                    'Integrate standard functions and find areas',
        'modules': [
            ('Differentiation', [
                lesson('Gradients and first principles',
                       'The derivative measures how fast a function changes. We find it by taking the gradient of a '
                       'chord and letting the chord shrink to a single point.',
                       r'\( f\'(x) = \lim_{h \to 0} \frac{f(x+h) - f(x)}{h} \)',
                       r'For \( f(x) = x^2 \): \( \frac{(x+h)^2 - x^2}{h} = 2x + h \to 2x \) as \( h \to 0 \).',
                       r'Use first principles to differentiate \( f(x) = 3x \).',
                       r'\( \frac{3(x+h) - 3x}{h} = 3 \), so \( f\'(x) = 3 \).'),
                lesson('The power rule',
                       'Differentiating from first principles every time is slow. The power rule gives the answer '
                       'for any power of x in one step.',
                       r'If \( y = ax^n \) then \( \frac{dy}{dx} = anx^{n-1} \).',
                       r'\( y = 4x^3 - 5x + 7 \) gives \( \frac{dy}{dx} = 12x^2 - 5 \).',
                       r'Differentiate \( y = 2x^5 + x^{-1} \).',
                       r'\( \frac{dy}{dx} = 10x^4 - x^{-2} \).'),
                lesson('Stationary points',
                       'At a maximum or minimum the tangent is horizontal, so the gradient is zero. The second '
                       'derivative tells us which kind of point it is.',
                       r'Solve \( \frac{dy}{dx} = 0 \); if \( \frac{d^2y}{dx^2} > 0 \) it is a minimum, if \( < 0 \) a maximum.',
                       r'\( y = x^2 - 6x \): \( 2x - 6 = 0 \) gives \( x = 3 \), and \( y\'\' = 2 > 0 \), so a minimum at (3, -9).',
                       r'Find and classify the stationary point of \( y = 8x - x^2 \).',
                       r'\( 8 - 2x = 0 \Rightarrow x = 4 \); \( y\'\' = -2 < 0 \), a maximum at (4, 16).'),
            ]),
            ('Integration', [
                lesson('Integration as the reverse of differentiation',
                       'Integration undoes differentiation. Because constants vanish when we differentiate, every '
                       'indefinite integral needs a constant c.',
                       r'\( \int ax^n\,dx = \frac{a}{n+1}x^{n+1} + c \) for \( n \neq -1 \).',
                       r'\( \int (6x^2 + 2)\,dx = 2x^3 + 2x + c \).',
                       r'Find \( \int (4x^3 - 3)\,dx \).',
                       r'\( x^4 - 3x + c \).'),
                lesson('Definite integrals and area',
                       'A definite integral has limits. Evaluating it gives the area between the curve and the '
                       'x-axis, counted negative below the axis.',
                       r'\( \int_a^b f(x)\,dx = F(b) - F(a) \) where \( F \) is any antiderivative.',
                       r'\( \int_0^2 3x^2\,dx = [x^3]_0^2 = 8 \).',
                       r'Find the area under \( y = 2x \) from \( x = 1 \) to \( x = 3 \).',
                       r'\( [x^2]_1^3 = 9 - 1 = 8 \) square units.'),
                lesson('Exam technique for calculus',
                       'Most lost marks come from skipped steps, not hard ideas. Write each step on its own line '
                       'and state what you are doing.',
                       'Show the derivative, the equation you solve, and the conclusion in words.',
                       'For a stationary point question: differentiate, set to zero, solve, test with the second '
                       'derivative, then give the coordinates.',
                       'Why do examiners ask for the nature of a stationary point?',
                       'Because a zero gradient alone could be a maximum, a minimum or a point of inflection.'),
            ]),
        ],
    },
    {
        'subject': 'physics', 'tutor': 'joseph.tembo@catchup.example', 'level': 'both', 'year': '',
        'title': 'Mechanics: Forces and Motion',
        'summary': 'Kinematics, Newton\'s laws, energy and momentum, explained step by step.',
        'outcomes': 'Use the SUVAT equations\nApply Newton\'s three laws\nUse conservation of energy and momentum',
        'modules': [
            ('Motion', [
                lesson('Displacement, velocity and acceleration',
                       'Motion is described by three vector quantities. Velocity is the rate of change of '
                       'displacement, and acceleration is the rate of change of velocity.',
                       'Speed is a scalar; velocity has a direction. A car turning a corner at steady speed is accelerating.',
                       r'A cyclist goes from 2 m/s to 10 m/s in 4 s: \( a = \frac{10 - 2}{4} = 2 \) m/s².',
                       'Can an object have zero velocity but non-zero acceleration?',
                       'Yes. A ball thrown upwards has zero velocity at the top but still accelerates at 9.81 m/s² downwards.'),
                lesson('The SUVAT equations',
                       'For constant acceleration, five quantities (s, u, v, a, t) are linked by four equations. '
                       'Pick the one that leaves out the quantity you do not know and do not need.',
                       r'\( v = u + at \), \( s = ut + \tfrac12 at^2 \), \( v^2 = u^2 + 2as \), \( s = \tfrac{(u+v)}{2}t \).',
                       r'A stone drops from rest for 3 s: \( s = \tfrac12(9.81)(3^2) = 44.1 \) m.',
                       'A car brakes from 20 m/s to rest over 50 m. Find its deceleration.',
                       r'\( 0 = 20^2 + 2a(50) \Rightarrow a = -4 \) m/s².'),
                lesson('Projectiles',
                       'Horizontal and vertical motion are independent. Horizontally the velocity is constant; '
                       'vertically the object accelerates at g.',
                       'Split the initial velocity into components and treat each direction separately.',
                       'A ball is kicked horizontally at 15 m/s from a 20 m cliff. Fall time: 2.02 s; distance: 30.3 m.',
                       'What is the horizontal acceleration of a projectile (ignoring air resistance)?',
                       'Zero. Only gravity acts, and it acts vertically.'),
            ]),
            ('Forces and energy', [
                lesson('Newton\'s laws of motion',
                       'Forces change motion. Newton\'s three laws let us predict exactly how.',
                       r'Resultant force \( F = ma \). Forces in a Newton third-law pair act on different objects.',
                       'A 1200 kg car with 3000 N driving force and 600 N drag accelerates at 2400/1200 = 2 m/s².',
                       'Why does a book on a table not accelerate?',
                       'The weight and the normal reaction balance, so the resultant force is zero.'),
                lesson('Work, energy and power',
                       'Work is done when a force moves its point of application. Energy is conserved, only '
                       'changing form.',
                       r'\( W = Fs\cos\theta \), \( E_k = \tfrac12 mv^2 \), \( E_p = mgh \), \( P = \frac{W}{t} \).',
                       r'A 2 kg mass falls 5 m: \( E_p = 2 \times 9.81 \times 5 = 98.1 \) J becomes kinetic energy.',
                       'A 60 kg student climbs 4 m of stairs in 6 s. What is their power output?',
                       r'\( P = \frac{60 \times 9.81 \times 4}{6} \approx 392 \) W.'),
                lesson('Momentum and collisions',
                       'Momentum is mass times velocity. In any collision with no external force, total momentum '
                       'is conserved.',
                       r'\( p = mv \); total momentum before = total momentum after.',
                       'A 2 kg trolley at 3 m/s sticks to a stationary 1 kg trolley: v = 6/3 = 2 m/s.',
                       'Is kinetic energy conserved in that collision?',
                       'No. It falls from 9 J to 6 J; the rest becomes heat and sound. Only elastic collisions conserve it.'),
            ]),
        ],
    },
    {
        'subject': 'chemistry', 'tutor': 'chipo.phiri@catchup.example', 'level': 'a_level', 'year': 'as',
        'title': 'Physical Chemistry: Moles to Equilibrium',
        'summary': 'Amount of substance, energetics, rates and equilibrium for AS and A2.',
        'outcomes': 'Carry out mole calculations confidently\nUse Hess\'s law\nPredict shifts in equilibrium',
        'modules': [
            ('Amount of substance', [
                lesson('The mole',
                       'Chemists count particles in moles. One mole contains 6.02 × 10²³ particles, the Avogadro '
                       'constant.',
                       r'\( n = \frac{m}{M} \): moles = mass ÷ molar mass.',
                       '18 g of water (M = 18 g/mol) is 1 mole and contains 6.02 × 10²³ molecules.',
                       'How many moles are in 10 g of calcium carbonate (M = 100 g/mol)?',
                       '0.1 mol.'),
                lesson('Concentration and titrations',
                       'Solutions are measured by concentration in mol/dm³. Titrations use a known solution to '
                       'find an unknown one.',
                       r'\( n = c \times V \) with V in dm³.',
                       '25.0 cm³ of NaOH is neutralised by 20.0 cm³ of 0.100 mol/dm³ HCl: NaOH is 0.0800 mol/dm³.',
                       'How many moles are in 250 cm³ of 0.2 mol/dm³ solution?',
                       '0.250 × 0.2 = 0.05 mol.'),
                lesson('Empirical formulae',
                       'The empirical formula is the simplest whole-number ratio of atoms in a compound.',
                       'Divide each mass (or %) by the atomic mass, then divide by the smallest result.',
                       'A compound is 40% C, 6.7% H, 53.3% O: ratio 3.33 : 6.7 : 3.33 gives CH₂O.',
                       'A compound contains 2.4 g C and 0.6 g H. Find the empirical formula.',
                       'C: 0.2 mol, H: 0.6 mol, ratio 1 : 3, so CH₃.'),
            ]),
            ('Energetics and equilibrium', [
                lesson('Enthalpy changes',
                       'Reactions transfer energy to or from the surroundings. Exothermic reactions have a negative '
                       'enthalpy change.',
                       r'\( q = mc\Delta T \), then \( \Delta H = -\frac{q}{n} \).',
                       'Burning a fuel heats 100 g of water by 20 K: q = 100 × 4.18 × 20 = 8360 J.',
                       'Is bond breaking exothermic or endothermic?',
                       'Endothermic. Energy is needed to break bonds; forming bonds releases energy.'),
                lesson('Hess\'s law',
                       'The enthalpy change of a reaction depends only on the start and end, not the route.',
                       'Build an energy cycle and add the enthalpy changes around the alternative route.',
                       'Using enthalpies of formation: ΔH = Σ ΔHf(products) − Σ ΔHf(reactants).',
                       'Why can\'t we measure the enthalpy of formation of methane directly?',
                       'Carbon and hydrogen do not react cleanly to form only methane, so we use combustion data and Hess\'s law.'),
                lesson('Le Chatelier\'s principle',
                       'At dynamic equilibrium the forward and reverse rates are equal. If conditions change, the '
                       'position shifts to oppose the change.',
                       'Increasing pressure favours the side with fewer gas molecules.',
                       'N₂ + 3H₂ ⇌ 2NH₃: high pressure shifts equilibrium right, increasing the yield of ammonia.',
                       'Does a catalyst change the position of equilibrium?',
                       'No. It speeds up both directions equally, so equilibrium is reached faster but in the same position.'),
            ]),
        ],
    },
    {
        'subject': 'biology', 'tutor': 'natasha.zulu@catchup.example', 'level': 'both', 'year': '',
        'title': 'Cell Biology and Biochemistry',
        'summary': 'Cell structure, biological molecules and enzymes for A-level and first year.',
        'outcomes': 'Describe eukaryotic and prokaryotic cells\nExplain how enzymes work\nInterpret enzyme rate graphs',
        'modules': [
            ('Cells', [
                lesson('Eukaryotic and prokaryotic cells',
                       'All living things are made of cells. Eukaryotic cells have a nucleus and membrane-bound '
                       'organelles; prokaryotic cells do not.',
                       'Prokaryotes have 70S ribosomes and circular DNA; eukaryotes have 80S ribosomes and linear chromosomes.',
                       'A bacterium has a cell wall, plasmids and a flagellum but no mitochondria.',
                       'Name two structures found in plant cells but not animal cells.',
                       'A cellulose cell wall and chloroplasts (and usually a large permanent vacuole).'),
                lesson('The cell membrane',
                       'The fluid mosaic model describes a phospholipid bilayer with proteins floating in it.',
                       'Small non-polar molecules diffuse through; ions need channel or carrier proteins.',
                       'Glucose enters red blood cells by facilitated diffusion through carrier proteins.',
                       'Why is active transport different from facilitated diffusion?',
                       'Active transport moves substances against their concentration gradient and uses ATP.'),
                lesson('Microscopy and magnification',
                       'Microscopes let us see cells. Resolution, not magnification, limits the detail we see.',
                       r'Magnification = image size ÷ actual size.',
                       'An image 20 mm long of a 10 µm cell: 20 000 µm ÷ 10 µm = ×2000.',
                       'Why can an electron microscope see ribosomes but a light microscope cannot?',
                       'Electrons have a much shorter wavelength, giving far higher resolution.'),
            ]),
            ('Biological molecules and enzymes', [
                lesson('Proteins',
                       'Proteins are chains of amino acids joined by peptide bonds. Their shape decides their job.',
                       'Primary structure is the sequence; secondary, tertiary and quaternary structures are folding.',
                       'Haemoglobin has quaternary structure: four polypeptide chains each holding a haem group.',
                       'Which bonds hold the tertiary structure together?',
                       'Hydrogen bonds, ionic bonds and disulfide bridges, plus hydrophobic interactions.'),
                lesson('How enzymes work',
                       'Enzymes are biological catalysts. The substrate binds to the active site, forming an '
                       'enzyme-substrate complex.',
                       'Enzymes lower the activation energy. The induced fit model says the active site moulds around the substrate.',
                       'Amylase breaks starch into maltose in the mouth and small intestine.',
                       'Why is an enzyme specific to one substrate?',
                       'Only a substrate with a complementary shape fits the active site.'),
                lesson('Factors affecting enzyme activity',
                       'Temperature, pH and concentration all change the rate of an enzyme reaction.',
                       'Above the optimum temperature, the enzyme denatures: the active site changes shape for good.',
                       'Pepsin works best near pH 2 in the stomach; trypsin near pH 8 in the small intestine.',
                       'What does a competitive inhibitor do?',
                       'It binds to the active site and blocks the substrate; adding more substrate reduces its effect.'),
            ]),
        ],
    },
    {
        'subject': 'computer-science', 'tutor': 'mutale.mulenga@catchup.example', 'level': 'university', 'year': 'uni1',
        'title': 'Programming Fundamentals in Python',
        'summary': 'Variables, control flow, functions and data structures for first-year students.',
        'outcomes': 'Write clean Python programs\nUse loops, functions and lists\nReason about algorithm efficiency',
        'modules': [
            ('Basics', [
                lesson('Variables and types',
                       'A variable is a name that refers to a value. Python works out the type from the value.',
                       'Common types: int, float, str, bool. Use type() to check.',
                       '<pre><code>price = 80\nname = "Catch Up"\nprint(f"{name} costs K{price}")</code></pre>',
                       'What is the type of 7 / 2 in Python 3?',
                       'float (3.5). Use // for integer division.'),
                lesson('Decisions with if',
                       'Programs make choices with if, elif and else. Indentation marks each block.',
                       'Conditions evaluate to True or False; combine them with and, or, not.',
                       '<pre><code>mark = 72\nif mark >= 70:\n    grade = "A"\nelif mark >= 60:\n    grade = "B"\nelse:\n    grade = "C"</code></pre>',
                       'What does the code give for mark = 60?',
                       '"B", because 60 >= 60 is True.'),
                lesson('Loops',
                       'Loops repeat work. for loops go through a sequence; while loops run until a condition fails.',
                       'Use range(n) to count from 0 to n − 1.',
                       '<pre><code>total = 0\nfor n in range(1, 6):\n    total += n\nprint(total)  # 15</code></pre>',
                       'Write a loop that prints the even numbers from 2 to 10.',
                       'for n in range(2, 11, 2): print(n)'),
            ]),
            ('Functions and data', [
                lesson('Functions',
                       'Functions package code under a name, so it can be reused and tested.',
                       'Use def, give parameters, and return a result instead of printing inside.',
                       '<pre><code>def area(r):\n    return 3.14159 * r ** 2\n\nprint(area(2))</code></pre>',
                       'Why is returning a value better than printing it?',
                       'The caller can use, test or combine a returned value; printed output is lost.'),
                lesson('Lists and dictionaries',
                       'Lists keep items in order; dictionaries map keys to values for fast lookup.',
                       'Lists use [index]; dictionaries use [key].',
                       '<pre><code>scores = {"Ana": 81, "Ben": 67}\nscores["Chi"] = 74\nprint(max(scores, key=scores.get))</code></pre>',
                       'What does the example print?',
                       'Ana, the key with the highest value.'),
                lesson('Algorithm efficiency',
                       'Some solutions slow down sharply as the input grows. Big-O notation describes how.',
                       'Linear search is O(n); binary search on sorted data is O(log n).',
                       'Searching 1,000,000 sorted items takes at most about 20 steps with binary search.',
                       'Why must data be sorted for binary search?',
                       'Each step discards half the data by comparing with the middle item, which only works if order is known.'),
            ]),
        ],
    },
    {
        'subject': 'data-science', 'tutor': 'mwila.banda@catchup.example', 'level': 'university', 'year': 'uni2',
        'title': 'Introduction to Data Science',
        'summary': 'Descriptive statistics, data cleaning and your first machine-learning model.',
        'outcomes': 'Summarise data with statistics\nClean and explore a dataset\nTrain and evaluate a simple model',
        'modules': [
            ('Statistics for data', [
                lesson('Averages and spread',
                       'A dataset is summarised by a centre and a spread. The right choice depends on the shape '
                       'of the data.',
                       'The median resists outliers; the mean does not. Standard deviation measures typical distance from the mean.',
                       'Salaries K3k, K4k, K4k, K5k, K40k: mean K11.2k but median K4k, the fairer summary.',
                       'When would you report the median instead of the mean?',
                       'When the data is skewed or has outliers, such as incomes or house prices.'),
                lesson('Correlation',
                       'Correlation measures how strongly two variables move together, from −1 to +1.',
                       'Correlation does not prove causation; a third variable may drive both.',
                       'Ice cream sales and drownings both rise in hot weather, but one does not cause the other.',
                       'What does r = −0.9 tell you?',
                       'A strong negative linear relationship: as one variable rises, the other tends to fall.'),
                lesson('Probability distributions',
                       'Many measurements follow the normal distribution, the familiar bell curve.',
                       'About 68% of values lie within 1 standard deviation of the mean, 95% within 2.',
                       'Test scores with mean 60 and SD 10: about 95% of students score between 40 and 80.',
                       'What percentage of values lie above the mean in a normal distribution?',
                       '50%.'),
            ]),
            ('Machine learning basics', [
                lesson('Cleaning data',
                       'Real data has gaps, typos and duplicates. Cleaning usually takes most of a project\'s time.',
                       'Decide for each column: drop missing rows, fill with a median, or flag them.',
                       '<pre><code>import pandas as pd\ndf = pd.read_csv("marks.csv")\ndf = df.drop_duplicates()\ndf["score"] = df["score"].fillna(df["score"].median())</code></pre>',
                       'Why fill missing scores with the median rather than zero?',
                       'Zero would pretend the student scored nothing and drag the averages down unfairly.'),
                lesson('Your first model: linear regression',
                       'Linear regression fits a straight line that predicts one variable from another.',
                       r'\( \hat{y} = b_0 + b_1 x \), chosen to minimise the squared errors.',
                       'Predicting exam score from hours studied: score = 35 + 4.2 × hours.',
                       'Using that model, what score is predicted for 10 hours of study?',
                       '35 + 42 = 77.'),
                lesson('Evaluating a model',
                       'A model must be tested on data it has never seen, or it may simply memorise.',
                       'Split data into training and test sets; report accuracy (or error) on the test set only.',
                       'A classifier scoring 99% on training data but 60% on test data is overfitting.',
                       'What is overfitting?',
                       'When a model learns noise in the training data and fails to generalise to new data.'),
            ]),
        ],
    },
]
