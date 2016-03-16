import matplotlib.pyplot as plt
import numpy as np

class AlbersEqualAreaProjection(object):
    def __init__(self, ra_0, dec_0, dec_1, dec_2):
        """Albers Equal Area Projection.

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
        # Snyder 1987, eq. 14-1 to 14-6.
        self.ra_0 = ra_0
        self.dec_0 = dec_0
        self.dec_1 = dec_1 # dec1 and dec2 only needed for __repr__
        self.dec_2 = dec_2
        self.deg2rad = np.pi/180

        self.n = (np.sin(dec_1 * self.deg2rad) + np.sin(dec_2 * self.deg2rad)) / 2
        self.C = np.cos(dec_1 * self.deg2rad)**2 + 2 * self.n * np.sin(dec_1 * self.deg2rad)
        self.rho_0 = self.__rho__(dec_0)

    def __rho__(self, dec):
        return np.sqrt(self.C - 2 * self.n * np.sin(dec * self.deg2rad)) / self.n

    def __call__(self, ra, dec, inverse=False):
        """Convert RA/Dec into map coordinates, or the reverse.

        Args:
            ra:  float or array of floats
            dec: float or array of floats
            inverse: if True, convert from map coordinates to RA/Dec

        Returns:
            x,y with the same format as ra/dec
        """
        if not inverse:

            ra_ = np.array([ra - self.ra_0]) * -1 # inverse for RA
            # check that ra_ is between -180 and 180 deg
            ra_[ra_ < -180 ] += 360
            ra_[ra_ > 180 ] -= 360

            theta = self.n * ra_[0]
            rho = self.__rho__(dec)
            return rho*np.sin(theta * self.deg2rad), self.rho_0 - rho*np.cos(theta * self.deg2rad)
        else:
            # ra/dec actually x/y
            rho = np.sqrt(ra**2 + (self.rho_0 - dec)**2)
            theta = np.arctan(ra/(self.rho_0 - dec)) / self.deg2rad
            return self.ra_0 - theta/self.n, np.arcsin((self.C - (rho * self.n)**2)/(2*self.n)) / self.deg2rad

    def __repr__(self):
        return "AlbersEqualAreaProjection(%r, %r, %r, %r)" % (self.ra_0, self.dec_0, self.dec_1, self.dec_2)

    def getMeridianPatches(self, meridians, **kwargs):
        """Get meridian lines in matplotlib format.

        Meridian lines in conics are circular arcs, appropriate
        matplotlib.patches will be return

        Args:
            meridians: list of declinations
            **kwargs: matplotlib.patches.Arc parameters

        Returns:
            matplotlib.PatchCollection
        """
        from matplotlib.patches import Arc
        from matplotlib.collections import PatchCollection

        # get opening angle
        origin = (0, self.rho_0)
        top_left = self.__call__(self.ra_0 - 180, 90)
        angle_limit = 180 - np.arctan2(origin[0]-top_left[0], origin[1]-top_left[1])/self.deg2rad
        angle = 90
        if self.n < 0:
            angle = -90
            angle_limit = 180 - angle_limit

        # get radii
        _, y = self.__call__(self.ra_0, meridians)
        radius = np.abs(self.rho_0 - y)

        patches = [Arc(origin, 2*radius[m], 2*radius[m], angle=angle, theta1=-angle_limit, theta2=angle_limit, **kwargs) for m in xrange(len(meridians))]
        return PatchCollection(patches, match_original=True, zorder=patches[0].zorder)

    def getParallelPatches(self, parallels, **kwargs):
        """Get parallel lines in matplotlib format.

        Parallel lines in conics are straight, appropriate
        matplotlib.patches will be returned.

        Args:
            meridians: list of rectascensions
            **kwargs: matplotlib.collection.LineCollection parameters

        Returns:
            matplotlib.LineCollection
        """

        # remove duplicates
        parallels_ = np.unique(parallels % 360)

        # the outer boundaries need to be duplicated because the same
        # parallel appear on the left and the right side of the map
        if self.ra_0 < 180:
            outer = self.ra_0 - 180
        else:
            outer = self.ra_0 + 180
        parallels_ = np.array(list(parallels_) + [outer])

        from matplotlib.collections import LineCollection
        top = self.__call__(parallels_, 90)
        bottom = self.__call__(parallels_, -90)
        x_ = np.dstack((top[0], bottom[0]))[0]
        y_ = np.dstack((top[1], bottom[1]))[0]
        return LineCollection(np.dstack((x_, y_)), color='k', **kwargs)

    def findIntersectionAtX(self, x, ylim, ra=None, dec=None):
        """Find intersection of meridian or parallel with a vertical line.

        Uses analytic solutions for intersections with medidian arcs or
        Newton solver for intersections with parallel lines.

        Args:
            x: x coordinate of the vertical line
            ylim: range in y for the vertical line
            ra: if not None, search for a parallel at this ra to intersect
            dec: if not None, search for a meridian at this dec to intersect

        Returns:
            float or None (if not solution was found)
        """
        from scipy.optimize import newton
        if dec is not None:
            # analytic solution for intersection of circle with line at x
            r = np.abs(self.rho_0 - self.__call__(self.ra_0, dec)[1])
            if np.abs(x) > np.abs(r):
                return None
            if self.rho_0 >= 0:
                return self.rho_0 - np.sqrt(r**2 - x**2)
            else:
                return np.sqrt(r**2 - x**2) + self.rho_0
        if ra is not None:
            try:
                return newton(lambda y: self.__call__(x,y,inverse=True)[0] - ra, (ylim[0] + ylim[1])/2)
            except RuntimeError:
                return None
        raise NotImplementedError("specify either RA or Dec")

    def findIntersectionAtY(self, y, xlim, ra=None, dec=None):
        """Find intersection of meridian or parallel with a horizontal line.

        Uses analytic solutions for intersections with medidian arcs or
        Newton solver for intersections with parallel lines.

        Args:
            y: y coordinate of the horizontal line
            xlim: range in x for the horizontal line
            ra: if not None, search for a parallel at this ra to intersect
            dec: if not None, search for a meridian at this dec to intersect

        Returns:
            float or None (if not solution was found)
        """
        from scipy.optimize import newton
        if dec is not None:
            # analytic solution for intersection of circle with line at x
            r = np.abs(self.rho_0 - self.__call__(self.ra_0, dec)[1])
            if np.abs(y) > np.abs(r):
                return None
            if self.rho_0 >= 0:
                return self.rho_0 - np.sqrt(r**2 - y**2)
            else:
                return np.sqrt(r**2 - y**2) + self.rho_0
        if ra is not None:
            try:
                return newton(lambda x: self.__call__(x,y,inverse=True)[0] - ra, (xlim[0] + xlim[1])/2)
            except RuntimeError:
                return None
        raise NotImplementedError("specify either RA or Dec")


##### Start of free methods #####

def setMeridianPatches(ax, proj, meridians, **kwargs):
    """Add meridian lines to matplotlib axes.

    Meridian lines in conics are circular arcs, appropriate
    matplotlib.patches will be added to given ax.

    Args:
        ax: matplotlib axes
        proj: a projection class
        meridians: list of declinations
        **kwargs: matplotlib.patches.Arc parameters

    Returns:
        None
    """
    patches = proj.getMeridianPatches(meridians, **kwargs)
    ax.add_collection(patches)

def setParallelPatches(ax, proj, parallels, **kwargs):
    """Add parallel lines to matplotlib axes.

    Parallel lines in conics are straight, appropriate
    matplotlib.patches will be added to given ax.

    Args:
        ax: matplotlib axes
        proj: a projection class
        meridians: list of rectascensions
        **kwargs: matplotlib.collection.LineCollection parameters

    Returns:
        None
    """
    patches = proj.getParallelPatches(parallels, **kwargs)
    ax.add_collection(patches)

def degFormatter(deg):
    """Default formatter for map labels.

    Args:
        deg: float
    Returns:
        string
    """
    return "%d$^\circ$" % deg

def pmDegFormatter(deg):
    """String formatter for "+-%d^\circ"

    Args:
        deg: float

    Return:
        String
    """
    format = "%d$^\circ$"
    if deg > 0:
        format = "$+$" + format
    if deg < 0:
        format = "$-$" + format
    return format % np.abs(deg)

def hourAngleFormatter(ra):
    """String formatter for "hh:mm"

    Args:
        deg: float

    Return:
        String
    """
    if ra < 0:
        ra += 360
    hours = int(ra)/15
    minutes = int(float(ra - hours*15)/15 * 60)
    minutes = '{:>02}'.format(minutes)
    return "%d:%sh" % (hours, minutes)

def setMeridianLabels(ax, proj, meridians, loc="left", fmt=degFormatter, **kwargs):
    """Add labels for meridians to matplotlib axes.

    Args:
        ax: matplotlib axes
        proj: a projection class
        meridians: list of rectascensions
        loc: "left" or "right"
        fmt: string formatter for labels
        **kwargs: matplotlib tick parameters

    Returns:
        None
    """

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()

    if loc == "left":
        ticks = []
        labels = []
        for m in meridians:
            tick = proj.findIntersectionAtX(xlim[0], ylim, dec=m)
            if tick is not None:
                ticks.append(tick)
                labels.append(fmt(m))
        ax.set_yticks(ticks)
        ax.set_yticklabels(labels, **kwargs)

    if loc == "right":
        ticks = []
        labels = []
        for m in meridians:
            tick = proj.findIntersectionAtX(xlim[1], ylim, dec=m)
            if tick is not None:
                ticks.append(tick)
                labels.append(fmt(m))
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        ax.set_yticks(ticks)
        ax.set_yticklabels(labels, **kwargs)

    ax.set_ylim(ylim)

def setParallelLabels(ax, proj, parallels, loc="bottom", fmt=degFormatter, **kwargs):
    """Add labels for parallels to matplotlib axes.

    Args:
        ax: matplotlib axes
        proj: a projection class
        parallels: list of declinations
        loc: "top" or "bottom"
        fmt: string formatter for labels
        **kwargs: matplotlib tick parameters

    Returns:
        None
    """

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()

    # remove duplicates
    parallels_ = np.unique(parallels % 360)

    # the outer boundaries need to be duplicated because the same
    # parallel appears on the left and the right side of the map
    if proj.ra_0 < 180:
        outer = proj.ra_0 - 180
    else:
        outer = proj.ra_0 + 180
    parallels_ = np.array(list(parallels_) + [outer])

    if loc == "bottom":
        ticks = []
        labels = []
        for p in parallels_:
            p_ = p
            if p - proj.ra_0 < -180:
                p_ += 360
            if p - proj.ra_0 > 180:
                p_ -= 360
            tick = proj.findIntersectionAtY(ylim[0], xlim, ra=p_)
            if tick is not None:
                ticks.append(tick)
                labels.append(fmt(p))
        ax.set_xticks(ticks)
        ax.set_xticklabels(labels, **kwargs)

    if loc == "top":
        ticks = []
        labels = []
        for p in parallels_:
            p_ = p
            # center of map is at ra=ra_0: wrap it around
            if p - proj.ra_0 < -180:
                p_ += 360
            if p - proj.ra_0 > 180:
                p_ -= 360
            tick = proj.findIntersectionAtY(ylim[1], xlim, ra=p_)
            if tick is not None:
                ticks.append(tick)
                labels.append(fmt(p))
        ax.xaxis.tick_top()
        ax.xaxis.set_label_position("top")
        ax.set_xticks(ticks)
        ax.set_xticklabels(labels, **kwargs)

    ax.set_xlim(xlim)

def createAEAMap(ax, ra, dec, aea=None, ra0=None, dec0=None, pad=0.02, bgcolor='#aaaaaa'):
    """Set up map for AlbersEqualAreaProjection.

    The function preconfigures the matplotlib axes, determines the optimal
    standard parallels, and set the proper x/y limits to show all of ra/dec.

    As a simple recommendation, the standard parallels are chosen to be 1/7th
    closer to dec0 than the minimum and maximum declination in the data
    (Snyder 1987, page 99).

    Args:
        ax: matplotlib axes
        ra: list of rectascensions
        dec: list of declinations
        aea: if not None, use this projection to define x/y limits
        ra0: if not None, use this as reference RA
        dec0: if not None, use this as reference Dec
        pad: float, how much padding between data and map boundary

    Returns:
        AlbersEqualAreaProjection or aea
    """
    if bgcolor is not None:
        ax.set_axis_bgcolor(bgcolor)
    # remove ticks as they look odd with curved/angled parallels/meridians
    ax.xaxis.set_tick_params(which='both', length=0)
    ax.yaxis.set_tick_params(which='both', length=0)

    if aea is None:
        if ra0 is None:
            ra_ = np.array(ra)
            ra_[ra_ > 180] -= 360
            ra_[ra_ < -180] += 360
            ra0 = np.median(ra_)
        if dec0 is None:
            dec0 = np.median(dec)
        # determine standard parallels for AEA
        dec1, dec2 = dec.min(), dec.max()
        # move standard parallels 1/6 further in from the extremes
        # to minimize scale variations (Snyder 1987, section 14)
        delta_dec = (dec0 - dec1, dec2 - dec0)
        dec1 += delta_dec[0]/7
        dec2 -= delta_dec[1]/7

        # set up AEA map
        aea = AlbersEqualAreaProjection(ra0, dec0, dec1, dec2)

    # determine x/y limits
    x,y = aea(ra, dec)
    xmin, xmax = x.min(), x.max()
    ymin, ymax = y.min(), y.max()
    delta_xy = (xmax-xmin, ymax-ymin)
    xmin -= pad*delta_xy[0]
    xmax += pad*delta_xy[0]
    ymin -= pad*delta_xy[1]
    ymax += pad*delta_xy[1]
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    return aea

def cloneMap(ax0, ax):
    """Convenience function to copy the setup of a map axes.

    Note that this sets up the axis, in particular the x/y limits, but does
    not clone any content (data or meridian/parellel patches or labels).

    Args:
        ax0: previousely configured matplotlib axes
        ax: axes to be configured

    Returns:
        None
    """
    ax.set_axis_bgcolor(ax0.get_axis_bgcolor())
    # remove ticks as they look odd with curved/angled parallels/meridians
    ax.xaxis.set_tick_params(which='both', length=0)
    ax.yaxis.set_tick_params(which='both', length=0)
    # set x/y limits
    ax.set_xlim(ax0.get_xlim())
    ax.set_ylim(ax0.get_ylim())

def getCountAtLocations(ra, dec, nside=512, return_vertices=False):
    """Get number density of objects from RA/Dec in HealPix cells.

    Requires: healpy

    Args:
        ra: list of rectascensions
        dec: list of declinations
        nside: HealPix nside
        return_vertices: whether to also return the boundaries of HealPix cells

    Returns:
        bc, ra_, dec_, [vertices]
        bc: count of objects [per arcmin^2] in a HealPix cell if count > 0
        ra_: rectascension of the cell center (same format as ra/dec)
        dec_: declinations of the cell center (same format as ra/dec)
        vertices: (N,4,2), RA/Dec coordinates of 4 boundary points of cell
    """
    import healpy as hp
    # get healpix pixels
    ipix = hp.ang2pix(nside, (90-dec)/180*np.pi, ra/180*np.pi, nest=False)
    # count how often each pixel is hit
    bc = np.bincount(ipix)
    pixels = np.nonzero(bc)[0]
    bc = bc[bc>0] / hp.nside2resol(nside, arcmin=True)**2 # in arcmin^-2
    # get position of each pixel in RA/Dec
    theta, phi = hp.pix2ang(nside, pixels, nest=False)
    ra_ = phi*180/np.pi
    dec_ = 90 - theta*180/np.pi

    # get the vertices that confine each pixel
    # convert to RA/Dec (thanks to Eric Huff)
    if return_vertices:
        vertices = np.zeros((pixels.size, 4, 2))
        for i in xrange(pixels.size):
            corners = hp.vec2ang(np.transpose(hp.boundaries(nside,pixels[i])))
            vertices[i,:,0] = corners[1] * 180./np.pi
            vertices[i,:,1] = 90.0 - corners[0] * 180/np.pi
        return bc, ra_, dec_, vertices
    else:
        return bc, ra_, dec_

def plotHealpixPolygons(ax, projection, vertices, color=None, vmin=None, vmax=None, **kwargs):
    """Plot Healpix cell polygons onto map.

    Args:
        ax: matplotlib axes
        projection: map projection
        vertices: Healpix cell boundaries in RA/Dec, from getCountAtLocations()
        color: string or matplib color, or numeric array to set polygon colors
        vmin: if color is numeric array, use vmin to set color of minimum
        vmax: if color is numeric array, use vmin to set color of minimum
        **kwargs: matplotlib.collections.PolyCollection keywords
    Returns:
        matplotlib.collections.PolyCollection
    """
    from matplotlib.collections import PolyCollection
    vertices_ = np.empty_like(vertices)
    vertices_[:,:,0], vertices_[:,:,1] = projection(vertices[:,:,0], vertices[:,:,1])
    coll = PolyCollection(vertices_, array=color, **kwargs)
    coll.set_clim(vmin=vmin, vmax=vmax)
    coll.set_edgecolor("face")
    ax.add_collection(coll)
    return coll

def getMarkerSizeToFill(fig, ax, x, y):
    """Get the size of a marker so that data points can fill axes.

    Assuming that x/y span a rectangle inside of ax, this method computes
    a best guess of the marker size to completely fill the area.

    Note: The marker area calculation in matplotlib seems to assume a square
          shape. If others shapes are desired (e.g. 'h'), a mild increase in
          size will be necessary.

    Args:
        fig: matplotlib.figure
        ax: matplib.axes that should hold x,y
        x, y: list of map positions

    Returns:
        int, the size (actually: area) to be used for scatter(..., s= )
    """
    # get size of bounding box in pixels
    # from http://stackoverflow.com/questions/19306510/determine-matplotlib-axis-size-in-pixels
    from math import ceil
    bbox = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
    width, height = bbox.width, bbox.height
    width *= fig.dpi
    height *= fig.dpi
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    dx = x.max() - x.min()
    dy = y.max() - y.min()
    filling_x = dx / (xlim[1] - xlim[0])
    filling_y = dy / (ylim[1] - ylim[0])
    # assuming x,y to ~fill a rectangle: get the point density
    area = filling_x*filling_y * width * height
    s = area / x.size
    return int(ceil(s)) # round up to be on the safe side
