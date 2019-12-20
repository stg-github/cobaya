import pytest

from collections import OrderedDict
from cobaya.model import get_model
from cobaya.theory import Theory
from cobaya.likelihood import Likelihood
from cobaya.log import LoggedError
from .common import process_modules_path


# Aderived = 1
# Aout = [Ain]
# Bpar = 3
# Bout = (3, [Ain])
# Bderived = 10
# Cout = Bout

class A(Theory):
    def get_requirements(self):
        return {'Ain'}

    def calculate(self, state, want_derived=True, **params_values_dict):
        state['Aout'] = [self.provider.get_param('Ain')]
        if want_derived:
            state['derived'] = {'Aderived': 1}

    def get_Aresult(self):
        return self._current_state['Aout']

    def get_can_provide_params(self):
        return ['Aderived']


class B(Theory):
    params = {'Bpar': None, 'Bderived': {'derived': True}}

    def get_requirements(self):
        return {'Aderived', 'Aresult'}

    def calculate(self, state, want_derived=True, **params_values_dict):
        state['Bout'] = (self.provider.get_param('Aderived') * params_values_dict['Bpar']
                         , self.provider.get_Aresult())

        if want_derived:
            state['derived'] = {'Bderived': 10}

    def get_Bout(self):
        return self._current_state['Bout']


class B2(Theory):

    def get_requirements(self):
        return {'Aderived', 'Aresult', 'Bpar'}

    def calculate(self, state, want_derived=True, **params_values_dict):
        state['Bout'] = (self.provider.get_param('Aderived') * params_values_dict['Bpar']
                         , self.provider.get_Aresult())

        if want_derived:
            state['derived'] = {'Bderived': 10}

    def get_Bout(self):
        return self._current_state['Bout']


class A2(Theory):  # circular
    def get_requirements(self):
        return {'Ain', 'Bout'}

    def get_can_provide_params(self):
        return ['Aderived', 'Aresult']


class C(Theory):  # ambiguous

    def get_requirements(self):
        return {'Aresult'}

    def calculate(self, state, want_derived=True, **params_values_dict):
        state['Cout'] = (3, [5])

    def get_Bout(self):
        return self._current_state['Cout']


class Like(Likelihood):

    def get_requirements(self):
        return {'Bout'}

    def calculate(self, state, want_derived=True, **params_values_dict):
        res = self.provider.get_Bout()
        state["logp"] = res[0] + res[1][0]


info = {'likelihood': {'like': Like},
        'params': {'Bpar': 3, 'Ain': 5},
        'debug': False}


def _test_loglike(theories):
    for th in theories, theories[::-1]:
        info['theory'] = OrderedDict(th)
        model = get_model(info)

        assert model.loglikes({})[0] == 8, "test loglike failed for %s" % th


def test_dependencies(modules):
    info['modules'] = process_modules_path(modules)
    theories = [('A', A), ('B', B)]
    _test_loglike(theories)
    _test_loglike([('A', A), ('B', B2)])

    info['params']['Bderived'] = {'derived': True}
    info['theory'] = OrderedDict(theories)
    model = get_model(info)
    assert model.loglikes({})[1] == [10], "failed"
    info['params'].pop('Bderived')

    with pytest.raises(LoggedError) as e:
        _test_loglike([('A', A2), ('B', B)])
    assert "Circular dependency" in str(e.value)

    _test_loglike([('A', {'external': A}), ('B', B2)])

    with pytest.raises(LoggedError) as e:
        _test_loglike([('A', A), ('B', B2), ('C', C)])
    assert "Bout is provided by more than one component" in str(e.value)

    _test_loglike([('A', A), ('B', B2), ('C', {'external': C, 'provides': 'Bout'})])
    _test_loglike([('A', A), ('B', {'external': B2, 'provides': ['Bout']}),
                   ('C', {'external': C})])

    with pytest.raises(LoggedError) as e:
        _test_loglike([('A', A), ('B', {'external': B2, 'provides': ['Bout']}),
                       ('C', {'external': C, 'provides': ['Bout']})])
    assert "more than one component provides Bout" in str(e.value)


# test conditional requirements
class D(Theory):

    def calculate(self, state, want_derived=True, **params_values_dict):
        state['D'] = self.provider.get_Aresult()[0] * 2

    def get_result(self, result_name, **kwargs):
        if result_name == 'Dresult':
            return self._current_state['D']

    def get_can_provide(self):
        return ['Dresult']

    def needs(self, **needs):
        if 'Dresult' in needs:
            return {'Aresult'}


class E(Theory):

    def calculate(self, state, want_derived=True, **params_values_dict):
        state['E'] = self.provider.get_result('Dresult') * 2

    def get_Eresult(self):
        return self._current_state['E']

    def needs(self, **needs):
        if 'Eresult' in needs:
            return {'Dresult'}


class Like2(Likelihood):

    def get_requirements(self):
        return {'Dresult'}

    def calculate(self, state, want_derived=True, **params_values_dict):
        state["logp"] = self.provider.get_result('Dresult') * 2


class Like3(Likelihood):

    def get_requirements(self):
        return {'Eresult'}

    def calculate(self, state, want_derived=True, **params_values_dict):
        state["logp"] = self.provider.get_Eresult()


# circular
class F(Theory):

    def get_Fresult(self):
        pass

    def needs(self, **needs):
        if 'Fresult' in needs:
            return {'LikeDerived'}


class Like4(Likelihood):

    def get_requirements(self):
        return {'Fresult'}

    def get_LikeDerived(self):
        pass


info2 = {'likelihood': {'like': Like2},
         'params': {'Ain': 5},
         'debug': True, 'stop_at_error': True}


def _test_loglike2(theories):
    for th in theories, theories[::-1]:
        info2['theory'] = OrderedDict(th)
        model = get_model(info2)
        assert model.loglike()[0] == 20., "fail conditional dependency for %s" % th


def test_conditional_dependencies(modules):
    theories = [('A', A), ('D', D)]
    _test_loglike2(theories)

    theories = [('A', A), ('D', D), ('E', E)]
    with pytest.raises(LoggedError) as e:
        _test_loglike2(theories)
    assert "seems not to depend on any parameters" in str(e.value)

    info2['likelihood']['like'] = Like3
    theories = [('A', A), ('D', D), ('E', E)]
    _test_loglike2(theories)

    info2['likelihood']['like'] = Like4
    theories = [('A', A), ('E', E), ('F', F), ('D', D)]
    with pytest.raises(LoggedError) as e:
        _test_loglike2(theories)
    assert "Circular dependency" in str(e.value)

    from cobaya.theory import Theory

    class ACalculator(Theory):

        def initialize(self):
            """called from __init__ to initialize"""

        def initialize_with_provider(self, provider):
            """
            Initialization after other components initialized, using Provider class
            instance which is used to return any dependencies (see calculate below).
            """
            self.provider = provider

        def get_requirements(self):
            """
            Return dictionary of derived parameters or other quantities that are needed
            by this component and should be calculated by another theory class.
            """
            return {'b_derived': None}

        def needs(self, **requirements):
            if 'A' in requirements:
                # e.g. calculating A requires B computed using same kmax (default 10)
                return {'B': {'kmax': requirements['A'].get('kmax', 10)}}

        def get_can_provide_params(self):
            return ['Aderived']

        def calculate(self, state, want_derived=True, **params_values_dict):
            state['A'] = self.provider.get_B() * self.provider.get_param('b_derived')
            state['derived'] = {'Aderived': 10}

        def get_A(self, normalization=1):
            return self._current_state['A'] * normalization
