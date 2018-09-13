import numpy as np
import scipy.integrate
import scipy.optimize

DEG2RAD = np.pi/180

def _toArray(x):
    if isinstance(x, np.ndarray):
        return x, True
    if hasattr(x, '__iter__'):
        return np.array(x), True
    return np.array([x]), False

def ellipticity(a, b):
    return 1-np.abs(b/a)
def meanDistortion(a, b):
    return np.mean(ellipticity(a,b))
def maxDistortion(a,b):
    return np.max(ellipticity(a,b))
def stdDistortion(a,b):
    return (b/a).std() # include the sign
def stdScale(a,b):
    return (a*b).std()
def stdDistortionScale(a,b):
    return stdScale(a,b) + stdDistortion(a,b)

def _optimize_objective(x, proj_type, ra, dec, reduce_fct):
    proj = proj_type(*x)
    a, b = proj.distortion(ra, dec)
    return reduce_fct(a,b)

def _optimize(proj_cls, x0, ra, dec, reduce_fct, bounds=None):
    print ("optimizing parameters for %r" % proj_cls)
    from scipy.optimize import fmin_l_bfgs_b
    x, fmin, d = fmin_l_bfgs_b(_optimize_objective, x0, args=(proj_cls, ra, dec, reduce_fct), bounds=bounds, approx_grad=True)
    print ("Best objective %.6f at %r" % (fmin, x))
    return proj_cls(*x)


# metaclass for registration.
# see https://effectivepython.com/2015/02/02/register-class-existence-with-metaclasses/
from . import register_projection, projection_register
class Meta(type):
    def __new__(meta, name, bases, class_dict):
        cls = type.__new__(meta, name, bases, class_dict)
        register_projection(cls)
        return cls

class BaseProjection(object):
    """Projection base class

    NOTE: Do not directly derive from `BaseProjection`, use `Projection` instead.
    This will automatically register the projection and make it available to
    functions that query projections.

    Every projection needs to implement three methods:
    * `transform(self, ra, dec)`: mapping from ra/dec to map x/y
    * `invert(self, x, y)`: the inverse mapping from x/y to ra/dec
    * `contains(self, x, y)`: whether x/y is inside of map region

    All three methods accept either single number or arrays and return accordingly.
    """
    def transform(self, ra, dec):
        """Convert RA/Dec into map coordinates

        Args:
            ra:  float or array of floats
            dec: float or array of floats

        Returns:
            x,y with the same format as ra/dec
        """
        pass

    def invert(self, x, y):
        """Convert map coordinates into RA/Dec

        Args:
            x:  float or array of floats
            y: float or array of floats

        Returns:
            RA,Dec with the same format as x/y
        """
        pass

    def contains(self, x, y):
        """Test if x/y is a valid set of map coordinates

        Args:
            x:  float or array of floats
            y: float or array of floats

        Returns:
            Bool array with the same format as x/y
        """
        pass

    def _wrapRA(self, ra):
        ra_, isArray = _toArray(ra)
        ra_ = self.ra_0 - ra_ # inverse for RA
        # check that ra_ is between -180 and 180 deg
        ra_[ra_ < -180 ] += 360
        ra_[ra_ > 180 ] -= 360
        if isArray:
            return ra_
        return ra_[0]

    def _unwrapRA(self, ra):
        ra_, isArray = _toArray(ra)
        ra_ = self.ra_0 - ra_
        ra_ [ra_ < 0] += 360
        ra_ [ra_ > 360] -= 360
        if isArray:
            return ra_
        return ra_[0]

    def gradient(self, ra, dec, sep=1e-2, direction='parallel'):
        assert direction in ['parallel', 'meridian']

        ra_, isArray = _toArray(ra)
        dec_, isArray = _toArray(dec)

        # gradients in *positive* dec and *negative* ra
        if direction == 'parallel':
            test = np.empty((2, ra_.size))
            test[0] = ra_-sep/2
            test[1] = ra_+sep/2

            # check for points beyond -180 / 180
            mask = test[0] <= self.ra_0 - 180
            test[0][mask] = ra_[mask]
            mask = test[1] >= self.ra_0 + 180
            test[1][mask] = ra_[mask]

            x, y = self.transform(test, np.ones((2,ra_.size))*dec)
        else:
            test = np.empty((2, dec_.size))
            test[0] = dec_-sep/2
            test[1] = dec_+sep/2

            # check for points beyond -90 / 90
            mask = test[0] <= -90
            test[0][mask] = dec_[mask]
            mask = test[1] >= 90
            test[1][mask] = dec_[mask]

            x, y = self.transform(np.ones((2,dec_.size))*ra, test)

        sep = test[1] - test[0]
        x[0] = (x[1] - x[0])/sep # dx
        x[1] = (y[1] - y[0])/sep # dy
        if isArray:
            return x.T
        return x[:,0]

    def jacobian(self, ra, dec, sep=1e-2):
        dxy_dra= self.gradient(ra, dec, sep=sep, direction='parallel')
        dxy_ddec = self.gradient(ra, dec, sep=sep, direction='meridian')
        return np.dstack((dxy_dra, dxy_ddec))

    def distortion(self, ra, dec):
        # Snyder (1987, section 4)
        jac = self.jacobian(ra,dec)
        cos_phi = np.cos(dec * DEG2RAD)
        h = np.sqrt(jac[:,0,1]**2 + jac[:,1,1]**2)
        k = np.sqrt(jac[:,0,0]**2 + jac[:,1,0]**2) / cos_phi
        sin_t = (jac[:,1,1]*jac[:,0,0] - jac[:,0,1]*jac[:,1,0])/(h*k*cos_phi)
        a_ = np.sqrt(h*h + k*k + 2*h*k*sin_t)
        b_ = np.sqrt(h*h + k*k - 2*h*k*sin_t)
        a = (a_ + b_) / 2
        b = (a_ - b_) / 2
        s = h*k*sin_t
        return a, b

    @classmethod
    def optimize(cls, ra, dec, bounds=None, reduce_fct=meanDistortion):
        ra_ = np.array(ra)
        ra_[ra_ > 180] -= 360
        ra_[ra_ < -180] += 360
        ra0 = ra_.mean()
        if ra0 < 0:
            ra0 += 360
        x0 = np.array((ra0,))
        bounds = ((0, 360),)
        return _optimize(cls, x0, ra, dec, reduce_fct, bounds=bounds)

class Projection(BaseProjection, metaclass=Meta):
    pass


class ConicProjection(Projection):
    def __init__(self, ra_0, dec_0, dec_1, dec_2):
        self.ra_0 = ra_0
        self.dec_0 = dec_0
        self.dec_1 = dec_1
        self.dec_2 = dec_2

    @classmethod
    def optimize(cls, ra, dec, bounds=None, reduce_fct=meanDistortion):
        # for conics: need to determine central ra, dec plus two standard parallels
        # normalize ra
        ra_ = np.array(ra)
        ra_[ra_ > 180] -= 360
        ra_[ra_ < -180] += 360
        # weigh more towards the poles because that decreases distortions
        ra0 = (ra_ * dec).sum() / dec.sum()
        if ra0 < 0:
            ra0 += 360
        dec0 = np.median(dec)

        # determine standard parallels
        dec1, dec2 = dec.min(), dec.max()

        # move standard parallels 1/6 further in from the extremes
        # to minimize scale variations (Snyder 1987, section 14)
        delta_dec = (dec0 - dec1, dec2 - dec0)
        dec1 += delta_dec[0]/6
        dec2 -= delta_dec[1]/6

        x0 = np.array((ra0, dec0, dec1, dec2))
        bounds = ((0, 360), (-90,90),(-90,90), (-90,90))
        return _optimize(cls, x0, ra, dec, reduce_fct, bounds=bounds)


class Albers(ConicProjection):
    def __init__(self, ra_0, dec_0, dec_1, dec_2):
        """Albers Equal-Area conic projection

        AEA is a conic projection with an origin along the lines connecting
        the poles. It preserves relative area, but is not conformal,
        perspective or equistant.

        Its preferred use of for areas with predominant east-west extent
        at moderate latitudes.

        As a conic projection, it depends on two standard parallels, i.e.
        intersections of the cone with the sphere. To minimize scale variations,
        these standard parallels should be chosen as small as possible while
        spanning the range in declinations of the data.

        For details, see Snyder (1987, section 14).

        Args:
            ra_0: RA that maps onto x = 0
            dec_0: Dec that maps onto y = 0
            dec_1: lower standard parallel
            dec_2: upper standard parallel (must not be -dec_1)
        """
        super(Albers, self).__init__(ra_0, dec_0, dec_1, dec_2)

        # Snyder 1987, eq. 14-3 to 14-6.
        self.n = (np.sin(dec_1 * DEG2RAD) + np.sin(dec_2 * DEG2RAD)) / 2
        self.C = np.cos(dec_1 * DEG2RAD)**2 + 2 * self.n * np.sin(dec_1 * DEG2RAD)
        self.rho_0 = self._rho(dec_0)

    def _rho(self, dec):
        return np.sqrt(self.C - 2 * self.n * np.sin(dec * DEG2RAD)) / self.n

    def transform(self, ra, dec):
        ra_ = self._wrapRA(ra)
        # Snyder 1987, eq 14-1 to 14-4
        theta = self.n * ra_
        rho = self._rho(dec)
        return rho*np.sin(theta * DEG2RAD), self.rho_0 - rho*np.cos(theta * DEG2RAD)

    def contains(self, x, y):
        rho = np.sqrt(x**2 + (self.rho_0 - y)**2)
        inside = np.abs((self.C - (rho * self.n)**2)/(2*self.n)) <= 1
        if self.n >= 0:
            theta = np.arctan2(x, self.rho_0 - y) / DEG2RAD
        else:
            theta = np.arctan2(-x, -(self.rho_0 - y)) / DEG2RAD
        wedge = np.abs(theta) < np.abs(self.n*180)
        return inside & wedge

    def invert(self, x, y):
        # ra/dec actually x/y
        # Snyder 1987, eq 14-8 to 14-11
        rho = np.sqrt(x**2 + (self.rho_0 - y)**2)
        if self.n >= 0:
            theta = np.arctan2(x, self.rho_0 - y) / DEG2RAD
        else:
            theta = np.arctan2(-x, -(self.rho_0 - y)) / DEG2RAD
        ra = self._unwrapRA(theta/self.n)
        dec = np.arcsin((self.C - (rho * self.n)**2)/(2*self.n)) / DEG2RAD
        return ra, dec

    def __repr__(self):
        return "Albers(%r, %r, %r, %r)" % (self.ra_0, self.dec_0, self.dec_1, self.dec_2)

class LambertConformal(ConicProjection):
    def __init__(self, ra_0, dec_0, dec_1, dec_2):
        """Lambert Conformal conic projection

        LCC is a conic projection with an origin along the lines connecting
        the poles. It preserves angles, but is not equal-area,
        perspective or equistant.

        Its preferred use of for areas with predominant east-west extent
        at higher latitudes.

        As a conic projection, it depends on two standard parallels, i.e.
        intersections of the cone with the sphere. To minimize scale variations,
        these standard parallels should be chosen as small as possible while
        spanning the range in declinations of the data.

        For details, see Snyder (1987, section 15).

        Args:
            ra_0: RA that maps onto x = 0
            dec_0: Dec that maps onto y = 0
            dec_1: lower standard parallel
            dec_2: upper standard parallel (must not be -dec_1)
        """
        super(LambertConformal, self).__init__(ra_0, dec_0, dec_1, dec_2)

        # Snyder 1987, eq. 14-1, 14-2 and 15-1 to 15-3.
        self.dec_max = 89.99

        dec_1 *= DEG2RAD
        dec_2 *= DEG2RAD
        self.n = np.log(np.cos(dec_1)/np.cos(dec_2)) / \
        (np.log(np.tan(np.pi/4 + dec_2/2)/np.tan(np.pi/4 + dec_1/2)))
        self.F = np.cos(dec_1)*(np.tan(np.pi/4 + dec_1/2)**self.n)/self.n
        self.rho_0 = self._rho(dec_0)

    def _rho(self, dec):
        # check that dec is inside of -dec_max .. dec_max
        dec_ = np.array([dec], dtype='f8')
        dec_[dec_ < -self.dec_max] = -self.dec_max
        dec_[dec_ > self.dec_max] = self.dec_max
        return self.F / np.tan(np.pi/4 + dec_[0]/2 * DEG2RAD)**self.n

    def transform(self, ra, dec):
        ra_ = self._wrapRA(ra)
        theta = self.n * ra_
        rho = self._rho(dec)
        return rho*np.sin(theta * DEG2RAD), self.rho_0 - rho*np.cos(theta * DEG2RAD)

    def contains(self, x, y):
        rho = np.sqrt(x**2 + (self.rho_0 - y)**2) * np.sign(self.n)
        inside = np.abs(rho) < max(np.abs(self._rho(self.dec_max)), np.abs(self._rho(-self.dec_max)))
        if self.n >= 0:
            theta = np.arctan2(x, self.rho_0 - y) / DEG2RAD
        else:
            theta = np.arctan2(-x, -(self.rho_0 - y)) / DEG2RAD
        wedge = np.abs(theta) < np.abs(self.n*180)
        return inside & wedge

    def invert(self, x, y):
        rho = np.sqrt(x**2 + (self.rho_0 - y)**2) * np.sign(self.n)
        if self.n >= 0:
            theta = np.arctan2(x, self.rho_0 - y) / DEG2RAD
        else:
            theta = np.arctan2(-x, -(self.rho_0 - y)) / DEG2RAD
        ra = self._unwrapRA(theta/self.n)
        dec = (2 * np.arctan((self.F/rho)**(1./self.n)) - np.pi/2) / DEG2RAD
        return ra, dec

    def __repr__(self):
        return "LambertConformal(%r, %r, %r, %r)" % (self.ra_0, self.dec_0, self.dec_1, self.dec_2)


class Equidistant(ConicProjection):
    def __init__(self, ra_0, dec_0, dec_1, dec_2):
        """Equidistant conic projection

        Equistant conic is a projection with an origin along the lines connecting
        the poles. It preserves distances along the map, but is not conformal,
        perspective or equal-area.

        Its preferred use is for smaller areas with predominant east-west extent
        at moderate latitudes.

        As a conic projection, it depends on two standard parallels, i.e.
        intersections of the cone with the sphere.

        For details, see Snyder (1987, section 16).

        Args:
            ra_0: RA that maps onto x = 0
            dec_0: Dec that maps onto y = 0
            dec_1: lower standard parallel
            dec_2: upper standard parallel (must not be +-dec_1)
        """
        super(Equidistant, self).__init__(ra_0, dec_0, dec_1, dec_2)

        # Snyder 1987, eq. 14-3 to 14-6.
        self.n = (np.cos(dec_1 * DEG2RAD) - np.cos(dec_2 * DEG2RAD)) / (dec_2  - dec_1) / DEG2RAD
        self.G = np.cos(dec_1 * DEG2RAD)/self.n + (dec_1 * DEG2RAD)
        self.rho_0 = self._rho(dec_0)

    def _rho(self, dec):
        return self.G - (dec * DEG2RAD)

    def transform(self, ra, dec):
        ra_ = self._wrapRA(ra)
        # Snyder 1987, eq 16-1 to 16-4
        theta = self.n * ra_
        rho = self._rho(dec)
        return rho*np.sin(theta * DEG2RAD), self.rho_0 - rho*np.cos(theta * DEG2RAD)

    def contains(self, x, y):
        rho = np.sqrt(x**2 + (self.rho_0 - y)**2) * np.sign(self.n)
        rho_min = np.abs(self._rho(90))
        rho_max = np.abs(self._rho(-90))
        if rho_min > rho_max:
            rho_min, rho_max = rho_max, rho_min
        inside = (np.abs(rho) < rho_max) & (np.abs(rho) > rho_min)
        if self.n >= 0:
            theta = np.arctan2(x, self.rho_0 - y) / DEG2RAD
        else:
            theta = np.arctan2(-x, -(self.rho_0 - y)) / DEG2RAD
        wedge = np.abs(theta) < np.abs(self.n*180)
        return inside & wedge

    def invert(self, x, y):
        # Snyder 1987, eq 14-10 to 14-11
        rho = np.sqrt(x**2 + (self.rho_0 - y)**2) * np.sign(self.n)
        if self.n >= 0:
            theta = np.arctan2(x, self.rho_0 - y) / DEG2RAD
        else:
            theta = np.arctan2(-x, -(self.rho_0 - y)) / DEG2RAD
        ra = self._unwrapRA(theta/self.n),
        dec = (self.G - rho)/ DEG2RAD
        return ra, dec

    def __repr__(self):
        return "Equidistant(%r, %r, %r, %r)" % (self.ra_0, self.dec_0, self.dec_1, self.dec_2)


class Hammer(Projection):
    def __init__(self, ra_0):
        """Hammer projection

        Hammer's 2:1 ellipse modification of The Lambert azimuthal equal-area
        projection.

        Its preferred use is for all-sky maps with an emphasis on low latitudes.
        It reduces the distortion at the outer meridians and has an elliptical
        outline. The only free parameter is the reference RA `ra_0`.

        For details, see Snyder (1987, section 24).
        """
        self.ra_0 = ra_0

    def transform(self, ra, dec):
        ra_ = self._wrapRA(ra)
        x = 2*np.sqrt(2)*np.cos(dec * DEG2RAD) * np.sin(ra_/2 * DEG2RAD)
        y = np.sqrt(2)*np.sin(dec * DEG2RAD)
        denom = np.sqrt(1+ np.cos(dec * DEG2RAD) * np.cos(ra_/2 * DEG2RAD))
        return x/denom, y/denom

    def invert(self, x, y):
        dz = x*x/16 + y*y/4
        z = np.sqrt(1- dz)
        dec = np.arcsin(z*y) / DEG2RAD
        ra = 2*np.arctan(z*x / (2*(2*z*z - 1))) / DEG2RAD
        ra = self._unwrapRA(ra)
        return ra, dec

    def contains(self, x, y):
        dz = x*x/16 + y*y/4
        return dz <= 0.5

    def __repr__(self):
        return "Hammer(%r)" % self.ra_0


class HyperEllipticalProjection(Projection):

    def __init__(self, ra_0, alpha, k, gamma):
        self.ra_0 = ra_0
        self.alpha = alpha
        self.k = k
        self.gamma = gamma
        self.gamma_pow_k = gamma**k
        self.affine = np.sqrt(2 * self.gamma / np.pi)

    def transform(self, ra, dec):
        ra_, isArray = _toArray(ra)
        dec_, isArray = _toArray(dec)
        ra_ = self._wrapRA(ra_)
        y = self.Y(np.sin(np.abs(dec_ * DEG2RAD)))
        x = ra_ * DEG2RAD * (self.alpha + (1 - self.alpha) / self.gamma * self.elliptic(y)) * self.affine
        y *= np.sign(dec_) / self.affine
        if isArray:
            return x, y
        else:
            return x[0], y[0]

    def invert(self, x, y):
        y_, isArray = _toArray(y * self.affine)
        sinphi = self.sinPhiDiff(y_, 0)
        dec = np.sign(y) * np.arcsin(sinphi) / DEG2RAD

        x_, isArray = _toArray(x)
        ra = x_ / self.affine / (self.alpha + (1 - self.alpha) / self.gamma * self.elliptic(y_)) / DEG2RAD
        ra = self._unwrapRA(ra)
        if isArray:
            return  ra, dec
        else:
            return  ra[0], dec[0]

    def contains(self, x, y):
        return np.abs(x / np.sqrt(2*np.pi/self.gamma))**self.k + np.abs(y * self.affine)**self.k < self.gamma_pow_k

    def elliptic(self, y):
        """Returns (gamma^k - y^k)^1/k
        """
        y_,isArray = _toArray(y)

        f = (self.gamma_pow_k - y_**self.k)**(1/self.k)
        f[y_ < 0 ] = self.gamma
        #f[y > self.gamma] = 0

        if isArray:
            return f
        else:
            return f[0]

    def elliptic_scalar(self, y):
        """Returns (gamma^k - y^k)^1/k
        """
        # needs to be fast for integrator, hence non-vectorized version
        if y < 0:
            return self.gamma
        return (self.gamma_pow_k - y**self.k)**(1/self.k)

    def z(self, y):
        """Returns int_0^y (gamma^k - y_^k)^1/k dy_
        """
        if hasattr(y, "__iter__"):
            return np.array([self.z(_) for _ in y])

        f = scipy.integrate.quad(self.elliptic_scalar, 0, y)[0]

        # check integration errors ofat the limits
        lim1 = self.gamma * (self.alpha*y - 1) / (self.alpha - 1)
        lim2 = self.gamma * self.alpha*y / (self.alpha - 1)
        if f < lim2:
            return lim2
        if f > lim1:
            return lim1
        return f

    def sinPhiDiff(self, y, sinphi):
        return self.alpha*y - (self.alpha - 1) / self.gamma * self.z(y) - sinphi

    def Y(self, sinphi, eps=1e-5, max_iter=30):
        if hasattr(sinphi, "__iter__"):
            return np.array([self.Y(_) for _ in sinphi])

        y, it, delta = 0.01, 0, 2*eps
        while it < max_iter and np.abs(delta) > eps:
            delta = self.sinPhiDiff(y, sinphi) / (self.alpha + (1 - self.alpha) / self.gamma * self.elliptic(y))
            y -= delta

            if y >= self.gamma:
                return self.gamma
            if y <= 0:
                return 0.
            it += 1
        return y

class Tobler(HyperEllipticalProjection):
    """Tobler hyperelliptical projection.

    See Snyder (1993, p. 202) for details.
    """
    def __init__(self, ra_0):
        alpha, k, gamma = 0, 2.5, 1.183136
        super(Tobler, self).__init__(ra_0, alpha, k, gamma)

class Mollweide(HyperEllipticalProjection):
    def __init__(self, ra_0):
        alpha, k, gamma = 0, 2, 1.2731
        super(Mollweide, self).__init__(ra_0, alpha, k, gamma)

class Collignon(HyperEllipticalProjection):
    def __init__(self, ra_0, gamma=1.):
        alpha, k = 0, 1
        super(Collignon, self).__init__(ra_0, alpha, k, gamma)

class EckertII(HyperEllipticalProjection):
    def __init__(self, ra_0, gamma=1.):
        alpha, k = 0.5, 1
        super(EckertII, self).__init__(ra_0, alpha, k, gamma)

class EckertIV(HyperEllipticalProjection):
    def __init__(self, ra_0, gamma=1.):
        alpha, k = 0.5, 2
        super(EckertIV, self).__init__(ra_0, alpha, k, gamma)

class HyperCloid(HyperEllipticalProjection):
    def __init__(self, ra_0, gamma=1):
        alpha, k = 0, 1.5
        super(HyperCloid, self).__init__(ra_0, alpha, k, gamma)
