from numpy.testing import assert_equal, assert_raises, assert_allclose

from brian2 import *
from brian2.parsing.sympytools import str_to_sympy, sympy_to_str
from brian2.utils.logger import catch_logs

# We can only test C++ if weave is availabe
try:
    import scipy.weave
    codeobj_classes = [WeaveCodeObject, NumpyCodeObject]
except ImportError:
    # Can't test C++
    codeobj_classes = [NumpyCodeObject]


def test_constants_sympy():
    '''
    Make sure that symbolic constants are understood correctly by sympy
    '''
    assert sympy_to_str(str_to_sympy('1.0/inf')) == '0'
    assert sympy_to_str(str_to_sympy('sin(pi)')) == '0'
    assert sympy_to_str(str_to_sympy('log(e)')) == '1'


def test_constants_values():
    '''
    Make sure that symbolic constants use the correct values in code
    '''
    G = NeuronGroup(1, 'v : 1')
    G.v = 'pi'
    assert G.v == np.pi
    G.v = 'e'
    assert G.v == np.e
    G.v = 'inf'
    assert G.v == np.inf


def test_math_functions():
    '''
    Test that math functions give the same result, regardless of whether used
    directly or in generated Python or C++ code.
    '''
    test_array = np.array([-1, -0.5, 0, 0.5, 1])

    with catch_logs() as _:  # Let's suppress warnings about illegal values        
        for codeobj_class in codeobj_classes:
            
            # Functions with a single argument
            for func in [sin, cos, tan, sinh, cosh, tanh,
                         arcsin, arccos, arctan,
                         exp, log, log10,
                         np.sqrt, np.ceil, np.floor, np.abs]:
                
                # Calculate the result directly
                numpy_result = func(test_array)
                
                # Calculate the result in a somewhat complicated way by using a
                # subexpression in a NeuronGroup
                clock = Clock()
                if func.__name__ == 'absolute':
                    # we want to use the name abs instead of absolute
                    func_name = 'abs'
                else:
                    func_name = func.__name__
                G = NeuronGroup(len(test_array),
                                '''func = {func}(variable) : 1
                                   variable : 1'''.format(func=func_name),
                                   clock=clock,
                                   codeobj_class=codeobj_class)
                G.variable = test_array
                mon = StateMonitor(G, 'func', record=True)
                net = Network(G, mon)
                net.run(clock.dt)
                
                assert_allclose(numpy_result, mon.func_.flatten(),
                                err_msg='Function %s did not return the correct values' % func.__name__)
            
            # Functions/operators
            scalar = 3
            # TODO: We are not testing the modulo operator here since it does
            #       not work for double values in C
            for func, operator in [(np.power, '**')]:
                
                # Calculate the result directly
                numpy_result = func(test_array, scalar)
                
                # Calculate the result in a somewhat complicated way by using a
                # subexpression in a NeuronGroup
                clock = Clock()
                G = NeuronGroup(len(test_array),
                                '''func = variable {op} scalar : 1
                                   variable : 1'''.format(op=operator),
                                   clock=clock,
                                   codeobj_class=codeobj_class)
                G.variable = test_array
                mon = StateMonitor(G, 'func', record=True)
                net = Network(G, mon)
                net.run(clock.dt)
                
                assert_allclose(numpy_result, mon.func_.flatten(),
                                err_msg='Function %s did not return the correct values' % func.__name__)


def test_user_defined_function():
    @make_function(codes={
        'cpp':{
            'support_code':"""
                inline double usersin(double x)
                {
                    return sin(x);
                }
                """,
            'hashdefine_code':'',
            },
        })
    @check_units(x=1, result=1)
    def usersin(x):
        return np.sin(x)

    test_array = np.array([0, 1, 2, 3])
    for codeobj_class in codeobj_classes:
        G = NeuronGroup(len(test_array),
                        '''func = usersin(variable) : 1
                                  variable : 1''',
                        codeobj_class=codeobj_class)
        G.variable = test_array
        mon = StateMonitor(G, 'func', record=True)
        net = Network(G, mon)
        net.run(defaultclock.dt)

        assert_equal(np.sin(test_array), mon.func_.flatten())


def test_simple_user_defined_function():
    # Make sure that it's possible to use a Python function directly, without
    # additional wrapping
    @check_units(x=1, result=1)
    def usersin(x):
        return np.sin(x)

    test_array = np.array([0, 1, 2, 3])
    G = NeuronGroup(len(test_array),
                    '''func = usersin(variable) : 1
                              variable : 1''',
                    codeobj_class=NumpyCodeObject)
    G.variable = test_array
    mon = StateMonitor(G, 'func', record=True)
    net = Network(G, mon)
    net.run(defaultclock.dt)

    assert_equal(np.sin(test_array), mon.func_.flatten())

    # Check that it raises an error for C++
    if WeaveCodeObject in codeobj_classes:
        G = NeuronGroup(len(test_array),
                        '''func = usersin(variable) : 1
                              variable : 1''',
                        codeobj_class=WeaveCodeObject)
        mon = StateMonitor(G, 'func', record=True,
                           codeobj_class=WeaveCodeObject)
        net = Network(G, mon)
        # This looks a bit odd -- we have to get usersin into the namespace of
        # the lambda expression
        assert_raises(NotImplementedError,
                      lambda usersin: net.run(0.1*ms), usersin)


def test_manual_user_defined_function():
    # User defined function without any decorators
    def foo(x, y):
        return x + y + 3*volt
    orig_foo = foo
    # Since the function is not annotated with check units, we need to specify
    # both the units of the arguments and the return unit
    assert_raises(ValueError, lambda: Function(foo, return_unit=volt))
    assert_raises(ValueError, lambda: Function(foo, arg_units=[volt, volt]))
    foo = Function(foo, arg_units=[volt, volt], return_unit=volt)

    assert foo(1*volt, 2*volt) == 6*volt

    # Incorrect argument units
    assert_raises(DimensionMismatchError, lambda: NeuronGroup(1, '''
                       dv/dt = foo(x, y)/ms : volt
                       x : 1
                       y : 1''', namespace={'foo': foo}))

    # Incorrect output unit
    assert_raises(DimensionMismatchError, lambda: NeuronGroup(1, '''
                       dv/dt = foo(x, y)/ms : 1
                       x : volt
                       y : volt''', namespace={'foo': foo}))

    G = NeuronGroup(1, '''
                       func = foo(x, y) : volt
                       x : volt
                       y : volt''')
    G.x = 1*volt
    G.y = 2*volt
    mon = StateMonitor(G, 'func', record=True)
    net = Network(G, mon)
    net.run(defaultclock.dt)

    assert mon[0].func == [6] * volt

    # discard units
    foo.implementations.add_numpy_implementation(orig_foo,
                                                 discard_units=True)
    G = NeuronGroup(1, '''
                       func = foo(x, y) : volt
                       x : volt
                       y : volt''')
    G.x = 1*volt
    G.y = 2*volt
    mon = StateMonitor(G, 'func', record=True)
    net = Network(G, mon)
    net.run(defaultclock.dt)

    assert mon[0].func == [6] * volt

    # Test C++ implementation
    if WeaveCodeObject in codeobj_classes:
        code = {'support_code': '''
        inline double foo(const double x, const double y)
        {
            return x + y + 3;
        }
        '''}

        foo.implementations.add_implementations(codes={'cpp': code})

        G = NeuronGroup(1, '''
                           func = foo(x, y) : volt
                           x : volt
                           y : volt''',
                        codeobj_class=WeaveCodeObject)
        G.x = 1*volt
        G.y = 2*volt
        mon = StateMonitor(G, 'func', record=True)
        net = Network(G, mon)
        net.run(defaultclock.dt)
        assert mon[0].func == [6] * volt


def test_user_defined_function_discarding_units():
    # A function with units that should discard units also inside the function
    @make_function(discard_units=True)
    @check_units(v=volt, result=volt)
    def foo(v):
        return v + 3*volt  # this normally raises an error for unitless v

    assert foo(5*volt) == 8*volt

    # Test the function that is used during a run
    assert foo.implementations[NumpyCodeObject].get_code(None)(5) == 8


def test_user_defined_function_discarding_units_2():
    # Add a numpy implementation explicitly (as in TimedArray)
    unit = volt
    @check_units(v=volt, result=unit)
    def foo(v):
        return v + 3*unit  # this normally raises an error for unitless v

    foo = Function(pyfunc=foo)
    def unitless_foo(v):
        return v + 3

    foo.implementations.add_implementation('numpy', code=unitless_foo)

    assert foo(5*volt) == 8*volt

    # Test the function that is used during a run
    assert foo.implementations[NumpyCodeObject].get_code(None)(5) == 8

def test_function_implementation_container():
    import brian2.codegen.targets as targets

    class ACodeGenerator(CodeGenerator):
        class_name = 'A Language'

    class BCodeGenerator(CodeGenerator):
        class_name = 'B Language'

    class ACodeObject(CodeObject):
        generator_class = ACodeGenerator
        class_name = 'A'

    class A2CodeObject(CodeObject):
        generator_class = ACodeGenerator
        class_name = 'A2'

    class BCodeObject(CodeObject):
        generator_class = BCodeGenerator
        class_name = 'B'


    # Register the code generation targets
    _previous_codegen_targets = set(targets.codegen_targets)
    targets.codegen_targets = set([ACodeObject, BCodeObject])

    @check_units(x=volt, result=volt)
    def foo(x):
        return x
    f = Function(foo)

    container = f.implementations

    # inserting into the container with a CodeGenerator class
    container.add_implementation(BCodeGenerator, code='implementation B language')
    assert container[BCodeGenerator].get_code(None) == 'implementation B language'

    # inserting into the container with a CodeObject class
    container.add_implementation(ACodeObject, code='implementation A CodeObject')
    assert container[ACodeObject].get_code(None) == 'implementation A CodeObject'

    # inserting into the container with a name of a CodeGenerator
    container.add_implementation('A Language', 'implementation A Language')
    assert container['A Language'].get_code(None) == 'implementation A Language'
    assert container[ACodeGenerator].get_code(None) == 'implementation A Language'
    assert container[A2CodeObject].get_code(None) == 'implementation A Language'

    # inserting into the container with a name of a CodeObject
    container.add_implementation('B', 'implementation B CodeObject')
    assert container['B'].get_code(None) == 'implementation B CodeObject'
    assert container[BCodeObject].get_code(None) == 'implementation B CodeObject'

    assert_raises(KeyError, lambda: container['unknown'])

    # some basic dictionary properties
    assert len(container) == 4
    assert set((key for key in container)) == set(['A Language', 'B',
                                                   ACodeObject, BCodeGenerator])

    # Restore the previous codegeneration targets
    targets.codegen_targets = _previous_codegen_targets


if __name__ == '__main__':
    test_constants_sympy()
    test_constants_values()
    test_math_functions()
    test_user_defined_function()
    test_simple_user_defined_function()
    test_manual_user_defined_function()
    test_user_defined_function_discarding_units()
    test_user_defined_function_discarding_units_2()
    test_function_implementation_container()
